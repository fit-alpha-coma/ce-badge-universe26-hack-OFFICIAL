"""Copilot Pager wire protocol shared by MicroPython and desktop Python.

The protocol encrypts a compact JSON document with ChaCha20-Poly1305 and then
splits the sealed document into BLE-sized frames.  It deliberately depends only
on modules available in the badge firmware.
"""

import hashlib
import json
import os
import struct


PROTOCOL_VERSION = 1
MAX_PLAINTEXT = 16 * 1024
MAX_SEALED = MAX_PLAINTEXT + 12 + 16
DEFAULT_FRAME_PAYLOAD = 160

KIND_REQUEST = 1
KIND_DECISION = 2
KIND_CANCEL = 3
KIND_STATUS = 4

MAGIC = b"CP"
HEADER_FORMAT = ">2sBBB8sHH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

SERVICE_UUID = "6f8a0001-5c3e-4b6a-9d91-4f63746f5067"
REQUEST_UUID = "6f8a0002-5c3e-4b6a-9d91-4f63746f5067"
DECISION_UUID = "6f8a0003-5c3e-4b6a-9d91-4f63746f5067"
STATUS_UUID = "6f8a0004-5c3e-4b6a-9d91-4f63746f5067"


class ProtocolError(ValueError):
    pass


def _rotl32(value, bits):
    return ((value << bits) & 0xFFFFFFFF) | (value >> (32 - bits))


def _quarter_round(state, a, b, c, d):
    state[a] = (state[a] + state[b]) & 0xFFFFFFFF
    state[d] = _rotl32(state[d] ^ state[a], 16)
    state[c] = (state[c] + state[d]) & 0xFFFFFFFF
    state[b] = _rotl32(state[b] ^ state[c], 12)
    state[a] = (state[a] + state[b]) & 0xFFFFFFFF
    state[d] = _rotl32(state[d] ^ state[a], 8)
    state[c] = (state[c] + state[d]) & 0xFFFFFFFF
    state[b] = _rotl32(state[b] ^ state[c], 7)


def chacha20_block(key, counter, nonce):
    if len(key) != 32 or len(nonce) != 12:
        raise ProtocolError("ChaCha20 needs a 32-byte key and 12-byte nonce")
    constants = struct.unpack("<4I", b"expand 32-byte k")
    initial = list(constants + struct.unpack("<8I", key) + (counter,) + struct.unpack("<3I", nonce))
    state = initial[:]
    for _ in range(10):
        _quarter_round(state, 0, 4, 8, 12)
        _quarter_round(state, 1, 5, 9, 13)
        _quarter_round(state, 2, 6, 10, 14)
        _quarter_round(state, 3, 7, 11, 15)
        _quarter_round(state, 0, 5, 10, 15)
        _quarter_round(state, 1, 6, 11, 12)
        _quarter_round(state, 2, 7, 8, 13)
        _quarter_round(state, 3, 4, 9, 14)
    return struct.pack("<16I", *[((state[i] + initial[i]) & 0xFFFFFFFF) for i in range(16)])


def _chacha20_xor(key, nonce, data, counter=1):
    output = bytearray(len(data))
    offset = 0
    while offset < len(data):
        block = chacha20_block(key, counter, nonce)
        amount = min(64, len(data) - offset)
        for index in range(amount):
            output[offset + index] = data[offset + index] ^ block[index]
        offset += amount
        counter = (counter + 1) & 0xFFFFFFFF
    return bytes(output)


def _poly1305(key, message):
    if len(key) != 32:
        raise ProtocolError("Poly1305 needs a 32-byte key")
    r = int.from_bytes(key[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key[16:], "little")
    accumulator = 0
    prime = (1 << 130) - 5
    for offset in range(0, len(message), 16):
        block = message[offset : offset + 16]
        number = int.from_bytes(block + b"\x01", "little")
        accumulator = ((accumulator + number) * r) % prime
    return ((accumulator + s) & ((1 << 128) - 1)).to_bytes(16, "little")


def _pad16(data):
    missing = (-len(data)) % 16
    return b"\x00" * missing


def _constant_time_equal(left, right):
    if len(left) != len(right):
        return False
    different = 0
    for a, b in zip(left, right):
        different |= a ^ b
    return different == 0


def encrypt(key, nonce, plaintext, aad=b""):
    one_time_key = chacha20_block(key, 0, nonce)[:32]
    ciphertext = _chacha20_xor(key, nonce, plaintext)
    mac_data = (
        aad
        + _pad16(aad)
        + ciphertext
        + _pad16(ciphertext)
        + struct.pack("<QQ", len(aad), len(ciphertext))
    )
    return ciphertext, _poly1305(one_time_key, mac_data)


def decrypt(key, nonce, ciphertext, tag, aad=b""):
    one_time_key = chacha20_block(key, 0, nonce)[:32]
    mac_data = (
        aad
        + _pad16(aad)
        + ciphertext
        + _pad16(ciphertext)
        + struct.pack("<QQ", len(aad), len(ciphertext))
    )
    expected = _poly1305(one_time_key, mac_data)
    if not _constant_time_equal(expected, tag):
        raise ProtocolError("authentication failed")
    return _chacha20_xor(key, nonce, ciphertext)


def canonical_json(value):
    # MicroPython's json module does not consistently expose CPython's
    # separators/sort_keys keyword arguments, so keep the encoder local.
    def quote(text):
        output = ['"']
        for char in str(text):
            code = ord(char)
            if char == '"':
                output.append('\\"')
            elif char == "\\":
                output.append("\\\\")
            elif char == "\b":
                output.append("\\b")
            elif char == "\f":
                output.append("\\f")
            elif char == "\n":
                output.append("\\n")
            elif char == "\r":
                output.append("\\r")
            elif char == "\t":
                output.append("\\t")
            elif code < 32:
                output.append("\\u%04x" % code)
            else:
                output.append(char)
        output.append('"')
        return "".join(output)

    def encode(item):
        if item is None:
            return "null"
        if item is True:
            return "true"
        if item is False:
            return "false"
        if isinstance(item, str):
            return quote(item)
        if isinstance(item, (int, float)):
            return str(item)
        if isinstance(item, (list, tuple)):
            return "[" + ",".join(encode(child) for child in item) + "]"
        if isinstance(item, dict):
            return "{" + ",".join(
                quote(key) + ":" + encode(item[key]) for key in sorted(item)
            ) + "}"
        raise ProtocolError("unsupported JSON value")

    return encode(value).encode("utf-8")


def payload_digest(value):
    import binascii

    return binascii.hexlify(hashlib.sha256(canonical_json(value)).digest()).decode("ascii")


def _aad(kind, message_id):
    return MAGIC + bytes((PROTOCOL_VERSION, kind)) + message_id


def seal_json(key, kind, value, nonce=None):
    plaintext = canonical_json(value)
    if len(plaintext) > MAX_PLAINTEXT:
        raise ProtocolError("payload exceeds 16 KiB")
    message_id = hashlib.sha256(plaintext).digest()[:8]
    nonce = nonce if nonce is not None else os.urandom(12)
    ciphertext, tag = encrypt(key, nonce, plaintext, _aad(kind, message_id))
    return message_id, nonce + ciphertext + tag


def open_json(key, kind, message_id, sealed):
    if len(sealed) < 28 or len(sealed) > MAX_SEALED:
        raise ProtocolError("invalid sealed payload length")
    nonce = sealed[:12]
    ciphertext = sealed[12:-16]
    tag = sealed[-16:]
    plaintext = decrypt(key, nonce, ciphertext, tag, _aad(kind, message_id))
    if hashlib.sha256(plaintext).digest()[:8] != message_id:
        raise ProtocolError("message identifier mismatch")
    try:
        return json.loads(plaintext.decode("utf-8"))
    except (ValueError, UnicodeError) as error:
        raise ProtocolError("invalid JSON payload") from error


def encode_frames(kind, message_id, sealed, payload_size=DEFAULT_FRAME_PAYLOAD):
    if len(message_id) != 8:
        raise ProtocolError("message identifier must be 8 bytes")
    if payload_size < 1:
        raise ProtocolError("BLE frame payload is too small")
    count = max(1, (len(sealed) + payload_size - 1) // payload_size)
    if count > 512:
        raise ProtocolError("message needs too many BLE frames")
    frames = []
    for index in range(count):
        part = sealed[index * payload_size : (index + 1) * payload_size]
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            PROTOCOL_VERSION,
            kind,
            0,
            message_id,
            index,
            count,
        )
        frames.append(header + part)
    return frames


def seal_frames(key, kind, value, payload_size=DEFAULT_FRAME_PAYLOAD, nonce=None):
    message_id, sealed = seal_json(key, kind, value, nonce)
    return encode_frames(kind, message_id, sealed, payload_size)


class FrameAssembler:
    """Reassemble complete messages while rejecting malformed chunk streams."""

    def __init__(self):
        self._messages = {}

    def clear(self):
        self._messages = {}

    def feed(self, frame):
        if len(frame) < HEADER_SIZE:
            raise ProtocolError("frame is shorter than its header")
        magic, version, kind, _flags, message_id, index, count = struct.unpack(
            HEADER_FORMAT, frame[:HEADER_SIZE]
        )
        if magic != MAGIC or version != PROTOCOL_VERSION:
            raise ProtocolError("unsupported protocol frame")
        if count < 1 or count > 512 or index >= count:
            raise ProtocolError("invalid frame sequence")
        key = (kind, message_id)
        state = self._messages.get(key)
        if state is None:
            state = {"count": count, "parts": {}, "size": 0}
            self._messages[key] = state
        elif state["count"] != count:
            del self._messages[key]
            raise ProtocolError("frame count changed")
        part = bytes(frame[HEADER_SIZE:])
        existing = state["parts"].get(index)
        if existing is not None and existing != part:
            del self._messages[key]
            raise ProtocolError("conflicting duplicate frame")
        if existing is None:
            state["parts"][index] = part
            state["size"] += len(part)
        if state["size"] > MAX_SEALED:
            del self._messages[key]
            raise ProtocolError("assembled message is too large")
        if len(state["parts"]) != count:
            return None
        sealed = b"".join(state["parts"][part_index] for part_index in range(count))
        del self._messages[key]
        return kind, message_id, sealed
