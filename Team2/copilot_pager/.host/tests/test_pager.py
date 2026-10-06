import os
import sys
import tempfile
import unittest


HOST_ROOT = os.path.dirname(os.path.dirname(__file__))
APP_ROOT = os.path.dirname(HOST_ROOT)
sys.path.insert(0, os.path.join(HOST_ROOT, "src"))
sys.path.insert(0, APP_ROOT)

import pager_protocol as badge_protocol
import ble_transport
from copilot_pager_host import config, normalize, protocol


class CryptoTests(unittest.TestCase):
    def test_rfc_8439_aead_vector(self):
        key = bytes.fromhex(
            "808182838485868788898a8b8c8d8e8f"
            "909192939495969798999a9b9c9d9e9f"
        )
        nonce = bytes.fromhex("070000004041424344454647")
        aad = bytes.fromhex("50515253c0c1c2c3c4c5c6c7")
        plaintext = (
            b"Ladies and Gentlemen of the class of '99: If I could offer you only one "
            b"tip for the future, sunscreen would be it."
        )
        expected = bytes.fromhex(
            "d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d6"
            "3dbea45e8ca9671282fafb69da92728b1a71de0a9e060b2905d6a5b67ecd3b36"
            "92ddbd7f2d778b8c9803aee328091b58fab324e4fad675945585808b4831d7bc"
            "3ff4def08e4b7a9de576d26586cec64b6116"
        )
        expected_tag = bytes.fromhex("1ae10b594f09e26a7e902ecbd0600691")
        ciphertext, tag = badge_protocol.encrypt(key, nonce, plaintext, aad)
        self.assertEqual(expected, ciphertext)
        self.assertEqual(expected_tag, tag)
        self.assertEqual(plaintext, badge_protocol.decrypt(key, nonce, ciphertext, tag, aad))

    def test_desktop_and_badge_are_wire_compatible(self):
        key = bytes(range(32))
        value = {"id": "req-1", "decision": "allow", "text": "hello"}
        nonce = b"\x07" * 12
        message_id, sealed = badge_protocol.seal_json(
            key, badge_protocol.KIND_DECISION, value, nonce
        )
        self.assertEqual(
            value,
            protocol.open_json(key, protocol.KIND_DECISION, message_id, sealed),
        )
        host_id, host_sealed = protocol.seal_json(
            key, protocol.KIND_REQUEST, value, nonce
        )
        self.assertEqual(
            value,
            badge_protocol.open_json(key, badge_protocol.KIND_REQUEST, host_id, host_sealed),
        )

    def test_frames_reassemble_out_of_order_and_reject_tampering(self):
        key = bytes(range(32))
        value = {"text": "x" * 900}
        frames = protocol.seal_frames(key, protocol.KIND_REQUEST, value, payload_size=47)
        assembler = badge_protocol.FrameAssembler()
        complete = None
        for frame in reversed(frames):
            complete = assembler.feed(frame) or complete
        kind, message_id, sealed = complete
        self.assertEqual(value, badge_protocol.open_json(key, kind, message_id, sealed))
        damaged = bytearray(sealed)
        damaged[-1] ^= 1
        with self.assertRaises(badge_protocol.ProtocolError):
            badge_protocol.open_json(key, kind, message_id, bytes(damaged))


class NormalizeTests(unittest.TestCase):
    def test_command_request(self):
        request = normalize.normalize_hook(
            {
                "sessionId": "s1",
                "cwd": "/work/hello",
                "toolName": "bash",
                "permissionKind": "commands",
                "toolInput": {"command": "npm test"},
            }
        )
        self.assertEqual("hello", request["repo"])
        self.assertEqual("npm test", request["command"])
        self.assertTrue(request["allow_remote"])
        self.assertEqual(64, len(request["payload_digest"]))

    def test_cli_string_tool_args_are_parsed(self):
        request = normalize.normalize_hook(
            {
                "toolName": "bash",
                "toolArgs": '{"command":"printf hello","description":"demo"}',
            }
        )
        self.assertEqual("printf hello", request["command"])
        self.assertEqual("demo", request["arguments"]["description"])

    def test_sandbox_bypass_requires_laptop(self):
        request = normalize.normalize_hook(
            {
                "toolName": "bash",
                "toolInput": {"command": "curl example.com", "requestSandboxBypass": True},
            }
        )
        self.assertFalse(request["allow_remote"])
        self.assertIn("Sandbox", request["blocked_reason"])

    def test_vscode_pascal_case_tool_names_are_normalized(self):
        request = normalize.normalize_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "make test"},
            }
        )
        self.assertEqual("bash", request["tool_name"])
        self.assertEqual("make test", request["command"])

    def test_oversized_request_is_safe(self):
        request = normalize.normalize_hook(
            {"toolName": "edit", "toolInput": {"diff": "+" + "x" * 20000}}
        )
        self.assertTrue(request["truncated"])
        self.assertFalse(request["allow_remote"])
        self.assertLessEqual(len(protocol.canonical_json(request)), protocol.MAX_PLAINTEXT)

    def test_exact_hook_results(self):
        self.assertEqual({"behavior": "allow"}, normalize.hook_result("allow"))
        self.assertEqual({}, normalize.hook_result("defer"))
        self.assertEqual("deny", normalize.hook_result("deny")["behavior"])


class FakeUUID:
    def __init__(self, value):
        self.value = value

    def __bytes__(self):
        return bytes.fromhex(self.value.replace("-", ""))


class FakeBLE:
    def __init__(self):
        self.advertisement = None
        self.values = {}
        self.indications = []

    def active(self, _value):
        pass

    def irq(self, callback):
        self.callback = callback

    def gatts_register_services(self, _services):
        return ((1, 2, 3),)

    def gatts_set_buffer(self, *_args):
        pass

    def gatts_write(self, handle, value):
        self.values[handle] = bytes(value)

    def gatts_read(self, handle):
        return self.values[handle]

    def gatts_indicate(self, _connection, handle):
        self.indications.append(self.values[handle])

    def gatts_notify(self, *_args):
        pass

    def gap_advertise(self, interval, **values):
        self.advertisement = (interval, values)


class FakeBluetooth:
    FLAG_READ = 0x0002
    FLAG_WRITE_NO_RESPONSE = 0x0004
    FLAG_WRITE = 0x0008
    FLAG_NOTIFY = 0x0010
    FLAG_INDICATE = 0x0020
    UUID = FakeUUID

    def __init__(self):
        self.instance = None

    def BLE(self):
        self.instance = FakeBLE()
        return self.instance


class BadgeBleTests(unittest.TestCase):
    def make_transport(self):
        fake = FakeBluetooth()
        previous = sys.modules.get("bluetooth")
        sys.modules["bluetooth"] = fake
        transport = ble_transport.PagerTransport()
        transport.pairing = {
            "key": b"k" * 32,
            "device_id": "pager-12345678",
            "laptop": "test",
        }
        transport._start()
        return fake, previous, transport

    def restore_bluetooth(self, previous):
        if previous is None:
            sys.modules.pop("bluetooth", None)
        else:
            sys.modules["bluetooth"] = previous

    def test_gatt_registration_and_advertisements_fit_legacy_packets(self):
        fake, previous, transport = self.make_transport()
        try:
            self.assertTrue(transport.available)
            _interval, values = fake.instance.advertisement
            self.assertLessEqual(len(values["adv_data"]), 31)
            self.assertLessEqual(len(values["resp_data"]), 31)
            self.assertEqual((1, 2, 3), (transport._rx_handle, transport._tx_handle, transport._status_handle))
        finally:
            self.restore_bluetooth(previous)

    def test_encrypted_request_and_decision_round_trip_through_gatt(self):
        fake, previous, transport = self.make_transport()
        try:
            transport.connection = 7
            request = {
                "id": "request-1",
                "payload_digest": "ab" * 32,
                "tool_name": "bash",
            }
            events = []
            for frame in protocol.seal_frames(b"k" * 32, protocol.KIND_REQUEST, request):
                fake.instance.values[transport._rx_handle] = frame
                transport._irq(3, (7, transport._rx_handle))
                events.extend(transport.poll())
            received = [value for kind, value in events if kind == "request"]
            self.assertEqual("request-1", received[0]["id"])

            self.assertTrue(transport.send_decision(received[0], "allow"))
            while transport._outgoing or transport._indicating:
                transport.poll()
                if transport._indicating:
                    transport._irq(20, (7, transport._tx_handle, 0))
            assembler = protocol.FrameAssembler()
            complete = None
            for frame in fake.instance.indications:
                complete = assembler.feed(frame) or complete
            kind, message_id, sealed = complete
            decision = protocol.open_json(b"k" * 32, kind, message_id, sealed)
            self.assertEqual("allow", decision["decision"])
            self.assertEqual("request-1", decision["request_id"])
        finally:
            self.restore_bluetooth(previous)


class ConfigTests(unittest.TestCase):
    def test_config_is_private(self):
        old = os.environ.get("COPILOT_PAGER_HOME")
        with tempfile.TemporaryDirectory() as directory:
            os.environ["COPILOT_PAGER_HOME"] = directory
            value = config.new_config("pager-test", "11" * 32)
            config.save_config(value)
            self.assertEqual(value, config.load_config(required=True))
            if os.name != "nt":
                self.assertEqual(0o600, os.stat(config.config_path()).st_mode & 0o777)
        if old is None:
            os.environ.pop("COPILOT_PAGER_HOME", None)
        else:
            os.environ["COPILOT_PAGER_HOME"] = old


if __name__ == "__main__":
    unittest.main()
