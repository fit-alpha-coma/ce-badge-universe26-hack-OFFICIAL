"""Desktop implementation of the version 1 Copilot Pager protocol."""

import hashlib
import json
import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305


PROTOCOL_VERSION = 1
MAX_PLAINTEXT = 16 * 1024
MAX_SEALED = MAX_PLAINTEXT + 28
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


def canonical_json(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def payload_digest(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _aad(kind, message_id):
    return MAGIC + bytes((PROTOCOL_VERSION, kind)) + message_id


def seal_json(key, kind, value, nonce=None):
    plaintext = canonical_json(value)
    if len(plaintext) > MAX_PLAINTEXT:
        raise ProtocolError("payload exceeds 16 KiB")
    message_id = hashlib.sha256(plaintext).digest()[:8]
    nonce = nonce if nonce is not None else os.urandom(12)
    sealed = ChaCha20Poly1305(key).encrypt(nonce, plaintext, _aad(kind, message_id))
    return message_id, nonce + sealed


def open_json(key, kind, message_id, sealed):
    if len(sealed) < 28 or len(sealed) > MAX_SEALED:
        raise ProtocolError("invalid sealed payload length")
    nonce, ciphertext = sealed[:12], sealed[12:]
    try:
        plaintext = ChaCha20Poly1305(key).decrypt(
            nonce, ciphertext, _aad(kind, message_id)
        )
    except InvalidTag as error:
        raise ProtocolError("authentication failed") from error
    if hashlib.sha256(plaintext).digest()[:8] != message_id:
        raise ProtocolError("message identifier mismatch")
    try:
        return json.loads(plaintext.decode("utf-8"))
    except (ValueError, UnicodeError) as error:
        raise ProtocolError("invalid JSON payload") from error


def encode_frames(kind, message_id, sealed, payload_size=DEFAULT_FRAME_PAYLOAD):
    if len(message_id) != 8 or payload_size < 1:
        raise ProtocolError("invalid framing parameters")
    count = max(1, (len(sealed) + payload_size - 1) // payload_size)
    if count > 512:
        raise ProtocolError("message needs too many BLE frames")
    result = []
    for index in range(count):
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
        result.append(header + sealed[index * payload_size : (index + 1) * payload_size])
    return result


def seal_frames(key, kind, value, payload_size=DEFAULT_FRAME_PAYLOAD, nonce=None):
    message_id, sealed = seal_json(key, kind, value, nonce)
    return encode_frames(kind, message_id, sealed, payload_size)


class FrameAssembler:
    def __init__(self):
        self._messages = {}

    def clear(self):
        self._messages = {}

    def feed(self, frame):
        if len(frame) < HEADER_SIZE:
            raise ProtocolError("short frame")
        magic, version, kind, _flags, message_id, index, count = struct.unpack(
            HEADER_FORMAT, frame[:HEADER_SIZE]
        )
        if magic != MAGIC or version != PROTOCOL_VERSION:
            raise ProtocolError("unsupported protocol frame")
        if count < 1 or count > 512 or index >= count:
            raise ProtocolError("invalid frame sequence")
        key = (kind, message_id)
        state = self._messages.setdefault(key, {"count": count, "parts": {}, "size": 0})
        if state["count"] != count:
            del self._messages[key]
            raise ProtocolError("frame count changed")
        part = bytes(frame[HEADER_SIZE:])
        old = state["parts"].get(index)
        if old is not None and old != part:
            del self._messages[key]
            raise ProtocolError("conflicting duplicate frame")
        if old is None:
            state["parts"][index] = part
            state["size"] += len(part)
        if state["size"] > MAX_SEALED:
            del self._messages[key]
            raise ProtocolError("assembled message is too large")
        if len(state["parts"]) != count:
            return None
        sealed = b"".join(state["parts"][position] for position in range(count))
        del self._messages[key]
        return kind, message_id, sealed
