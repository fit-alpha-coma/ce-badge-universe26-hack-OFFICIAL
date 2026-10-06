"""Low-level BLE peripheral used by the Copilot Pager badge app."""

import binascii
import json

from pager_protocol import (
    DECISION_UUID,
    KIND_CANCEL,
    KIND_REQUEST,
    REQUEST_UUID,
    SERVICE_UUID,
    STATUS_UUID,
    FrameAssembler,
    HEADER_SIZE,
    ProtocolError,
    open_json,
    seal_frames,
)


PAIRING_FILE = "/state/copilot_pager.json"


def load_pairing(path=PAIRING_FILE):
    try:
        with open(path, "r") as source:
            value = json.load(source)
        key = binascii.unhexlify(value.get("key", ""))
        if len(key) != 32:
            return None
        return {
            "key": key,
            "device_id": str(value.get("device_id", "pager"))[:32],
            "laptop": str(value.get("laptop", "Laptop"))[:32],
        }
    except (OSError, ValueError, TypeError):
        return None


class PagerTransport:
    def __init__(self):
        self.pairing = load_pairing()
        self.available = False
        self.error = "Not paired" if self.pairing is None else "BLE unavailable"
        self.connection = None
        self._ble = None
        self._rx_handle = None
        self._tx_handle = None
        self._status_handle = None
        self._writes = []
        self._events = []
        self._outgoing = []
        self._indicating = False
        self._assembler = FrameAssembler()
        self.mtu = 23
        if self.pairing is not None:
            self._start()

    @property
    def connected(self):
        return self.connection is not None

    @property
    def device_id(self):
        if self.pairing is None:
            return "unpaired"
        return self.pairing["device_id"]

    @property
    def laptop(self):
        if self.pairing is None:
            return "No laptop"
        return self.pairing["laptop"]

    def _start(self):
        try:
            import bluetooth

            self._bluetooth = bluetooth
            self._ble = bluetooth.BLE()
            self._ble.active(True)
            self._ble.irq(self._irq)
            read = getattr(bluetooth, "FLAG_READ", 0x0002)
            write = getattr(bluetooth, "FLAG_WRITE", 0x0008)
            write_no_response = getattr(bluetooth, "FLAG_WRITE_NO_RESPONSE", 0x0004)
            notify = getattr(bluetooth, "FLAG_NOTIFY", 0x0010)
            indicate = getattr(bluetooth, "FLAG_INDICATE", 0x0020)
            service = (
                bluetooth.UUID(SERVICE_UUID),
                (
                    (bluetooth.UUID(REQUEST_UUID), write | write_no_response),
                    (bluetooth.UUID(DECISION_UUID), read | notify | indicate),
                    (bluetooth.UUID(STATUS_UUID), read | notify),
                ),
            )
            ((self._rx_handle, self._tx_handle, self._status_handle),) = (
                self._ble.gatts_register_services((service,))
            )
            try:
                self._ble.gatts_set_buffer(self._rx_handle, 512, False)
                self._ble.gatts_set_buffer(self._tx_handle, 512, False)
            except (AttributeError, ValueError):
                pass
            self._write_status("advertising")
            self.available = True
            self.error = ""
            self._advertise()
        except (ImportError, AttributeError, OSError, ValueError) as error:
            self.available = False
            self.error = "BLE: %s" % error

    def _advertising_payload(self, name=None, include_service=True):
        payload = bytearray()

        def field(kind, value):
            payload.extend(bytes((len(value) + 1, kind)) + value)

        field(0x01, b"\x06")
        if name:
            field(0x09, name.encode("utf-8")[:24])
        if include_service:
            try:
                field(0x07, bytes(self._bluetooth.UUID(SERVICE_UUID)))
            except (TypeError, ValueError):
                pass
        return payload

    def _advertise(self):
        if self._ble is None or not self.available:
            return
        suffix = self.device_id[-8:].upper()
        name = "CopilotPager-" + suffix
        try:
            # Legacy advertising packets are 31 bytes. Keep the service UUID in
            # the primary packet and put the human-readable name in scan data.
            self._ble.gap_advertise(
                250000,
                adv_data=self._advertising_payload(),
                resp_data=self._advertising_payload(name, include_service=False),
            )
        except TypeError:
            # Older builds without scan-response support still fit the service
            # and a short, device-specific name in one 31-byte packet.
            try:
                self._ble.gap_advertise(
                    250000,
                    adv_data=self._advertising_payload("CP-" + suffix[-4:]),
                )
            except (OSError, ValueError) as error:
                self.error = "Advertise: %s" % error
        except (OSError, ValueError) as error:
            self.error = "Advertise: %s" % error

    def _irq(self, event, data):
        # MicroPython bluetooth IRQ values are stable across btstack and NimBLE.
        if event == 1:  # _IRQ_CENTRAL_CONNECT
            self.connection = data[0]
            self.mtu = 23
            self._assembler.clear()
            self._write_status("connected")
            self._events.append(("connection", True))
        elif event == 2:  # _IRQ_CENTRAL_DISCONNECT
            self.connection = None
            self._indicating = False
            self._outgoing = []
            self._assembler.clear()
            self._write_status("advertising")
            self._events.append(("connection", False))
            self._advertise()
        elif event == 3:  # _IRQ_GATTS_WRITE
            if data[1] == self._rx_handle:
                try:
                    self._writes.append(bytes(self._ble.gatts_read(self._rx_handle)))
                except OSError:
                    pass
        elif event == 20:  # _IRQ_GATTS_INDICATE_DONE
            self._indicating = False
        elif event == 21:  # _IRQ_MTU_EXCHANGED
            self.mtu = max(23, int(data[1]))

    def _write_status(self, state):
        if self._ble is None or self._status_handle is None:
            return
        value = json.dumps(
            {"v": 1, "state": state, "device_id": self.device_id}
        ).encode("utf-8")
        try:
            self._ble.gatts_write(self._status_handle, value)
            if self.connection is not None:
                self._ble.gatts_notify(self.connection, self._status_handle, value)
        except OSError:
            pass

    def _consume_write(self, frame):
        try:
            complete = self._assembler.feed(frame)
            if complete is None:
                return
            kind, message_id, sealed = complete
            if kind not in (KIND_REQUEST, KIND_CANCEL):
                raise ProtocolError("unexpected host message")
            value = open_json(self.pairing["key"], kind, message_id, sealed)
            value["_message_id"] = binascii.hexlify(message_id).decode("ascii")
            self._events.append(("request" if kind == KIND_REQUEST else "cancel", value))
        except (ProtocolError, ValueError, TypeError) as error:
            self.error = "Protocol: %s" % error
            self._events.append(("error", self.error))

    def _send_next(self):
        if self.connection is None or self._indicating or not self._outgoing:
            return
        frame = self._outgoing.pop(0)
        try:
            self._ble.gatts_write(self._tx_handle, frame)
            self._ble.gatts_indicate(self.connection, self._tx_handle)
            self._indicating = True
        except (AttributeError, OSError):
            try:
                self._ble.gatts_notify(self.connection, self._tx_handle, frame)
            except OSError:
                self._outgoing = []

    def poll(self):
        while self._writes:
            self._consume_write(self._writes.pop(0))
        self._send_next()
        events = self._events
        self._events = []
        return events

    def send_decision(self, request, decision):
        if self.connection is None or self.pairing is None:
            return False
        value = {
            "v": 1,
            "request_id": request.get("id", ""),
            "payload_digest": request.get("payload_digest", ""),
            "decision": decision,
            "device_id": self.device_id,
        }
        try:
            self._outgoing.extend(
                seal_frames(
                    self.pairing["key"],
                    2,
                    value,
                    payload_size=max(1, min(160, self.mtu - 3 - HEADER_SIZE)),
                )
            )
            self._write_status("deciding")
            return True
        except (ProtocolError, OSError, ValueError) as error:
            self.error = "Decision: %s" % error
            return False

    def stop(self):
        if self._ble is not None:
            try:
                self._ble.gap_advertise(None)
                self._ble.active(False)
            except (OSError, ValueError):
                pass
