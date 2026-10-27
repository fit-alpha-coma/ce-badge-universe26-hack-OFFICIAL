"""BLE central and serialized approval queue."""

import asyncio
import time

from bleak import BleakClient, BleakScanner

from .protocol import (
    DECISION_UUID,
    KIND_DECISION,
    KIND_REQUEST,
    REQUEST_UUID,
    SERVICE_UUID,
    FrameAssembler,
    HEADER_SIZE,
    ProtocolError,
    open_json,
    seal_frames,
)


class PagerBridge:
    def __init__(self, config):
        self.config = config
        self.key = bytes.fromhex(config["key"])
        if len(self.key) != 32:
            raise RuntimeError("Pairing key is invalid")
        self.queue = asyncio.Queue()
        self.client = None
        self.connected = False
        self.current = None
        self.current_future = None
        self.disconnect_event = asyncio.Event()
        self.assembler = FrameAssembler()
        self.last_error = ""
        self.frame_payload = 3
        self.connect_lock = asyncio.Lock()
        self.inflight_calls = {}
        self.recent_calls = {}

    @staticmethod
    def _call_key(request):
        tool_call_id = str(request.get("tool_call_id") or "")
        if not tool_call_id:
            return None
        return (str(request.get("session_id") or ""), tool_call_id)

    def status(self):
        return {
            "connected": self.connected,
            "device_id": self.config["device_id"],
            "queued": self.queue.qsize() + (1 if self.current else 0),
            "last_error": self.last_error,
        }

    async def submit(self, request):
        request = dict(request)
        key = self._call_key(request)
        now = time.monotonic()
        self.recent_calls = {
            existing_key: value
            for existing_key, value in self.recent_calls.items()
            if value[1] > now
        }
        if key in self.recent_calls:
            return self.recent_calls[key][0]
        if key in self.inflight_calls:
            return await asyncio.wait_for(
                asyncio.shield(self.inflight_calls[key]), timeout=91.0
            )
        request["queue_position"] = self.queue.qsize() + (2 if self.current else 1)
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        if key is not None:
            self.inflight_calls[key] = future
        await self.queue.put((request, future))
        try:
            decision = await asyncio.wait_for(asyncio.shield(future), timeout=91.0)
            if key is not None:
                self.recent_calls[key] = (decision, time.monotonic() + 15.0)
            return decision
        except asyncio.TimeoutError:
            if not future.done():
                future.set_result("defer")
            return "defer"
        finally:
            if key is not None and self.inflight_calls.get(key) is future:
                self.inflight_calls.pop(key, None)

    async def run(self):
        connector = asyncio.create_task(
            self._maintain_connection(), name="copilot-pager-connect"
        )
        try:
            while True:
                request, future = await self.queue.get()
                self.current = request
                self.current_future = future
                self.disconnect_event.clear()
                try:
                    decision = await self._process(request)
                except Exception as error:
                    self.last_error = "%s: %s" % (type(error).__name__, error)
                    decision = "defer"
                if not future.done():
                    future.set_result(decision)
                self.current = None
                self.current_future = None
                self.queue.task_done()
        finally:
            connector.cancel()
            await asyncio.gather(connector, return_exceptions=True)

    async def _maintain_connection(self):
        while True:
            if not self.connected:
                try:
                    await self._connect(timeout=5.0)
                except Exception as error:
                    self.last_error = "%s: %s" % (type(error).__name__, error)
            await asyncio.sleep(1.0)

    async def _find(self, timeout):
        name = "CopilotPager-" + self.config["device_id"][-8:].upper()
        short_name = "CP-" + self.config["device_id"][-4:].upper()

        def match(device, advertisement):
            advertised_name = advertisement.local_name or device.name or ""
            services = {value.lower() for value in advertisement.service_uuids or ()}
            return advertised_name in (name, short_name) or SERVICE_UUID in services

        return await BleakScanner.find_device_by_filter(match, timeout=timeout)

    def _disconnected(self, _client):
        # A delayed callback from an old connection must not tear down a newer
        # connection established during retry.
        if self.client is not None and _client is not self.client:
            return
        self.connected = False
        self.disconnect_event.set()

    async def _discard_client(self, failed_client):
        if self.client is failed_client:
            self.client = None
            self.connected = False
        try:
            await failed_client.disconnect()
        except Exception:
            pass
        self.disconnect_event.clear()

    async def _connect(self, timeout=2.0):
        async with self.connect_lock:
            if self.client is not None and self.client.is_connected:
                self.connected = True
                return True
            device = await self._find(timeout)
            if device is None:
                self.last_error = "Paired badge was not found"
                return False
            client = BleakClient(
                device,
                disconnected_callback=self._disconnected,
                timeout=max(5.0, timeout),
            )
            try:
                await client.connect()
                await client.start_notify(DECISION_UUID, self._notification)
            except Exception:
                try:
                    await client.disconnect()
                except Exception:
                    pass
                raise
            self.client = client
            self.connected = True
            mtu = int(getattr(client, "mtu_size", 23) or 23)
            self.frame_payload = max(1, min(160, mtu - 3 - HEADER_SIZE))
            self.disconnect_event.clear()
            self.assembler.clear()
            self.last_error = ""
            return True

    def _notification(self, _sender, data):
        try:
            complete = self.assembler.feed(bytes(data))
            if complete is None:
                return
            kind, message_id, sealed = complete
            if kind != KIND_DECISION or self.current is None or self.current_future is None:
                return
            value = open_json(self.key, kind, message_id, sealed)
            decision = value.get("decision")
            if decision not in ("allow", "deny", "defer"):
                raise ProtocolError("unknown badge decision")
            if value.get("device_id") != self.config["device_id"]:
                raise ProtocolError("decision came from another badge")
            if value.get("request_id") != self.current.get("id"):
                raise ProtocolError("stale decision request identifier")
            if value.get("payload_digest") != self.current.get("payload_digest"):
                raise ProtocolError("stale decision payload digest")
            if not self.current_future.done():
                self.current_future.set_result(decision)
        except (ProtocolError, ValueError, TypeError) as error:
            self.last_error = "Rejected decision: %s" % error

    async def _send(self, request):
        frames = seal_frames(
            self.key, KIND_REQUEST, request, payload_size=self.frame_payload
        )
        for frame in frames:
            await self.client.write_gatt_char(REQUEST_UUID, frame, response=True)

    async def _process(self, request):
        # If no badge is already connected, fail back to the laptop quickly.
        try:
            connected = await asyncio.wait_for(
                self._connect(timeout=1.5), timeout=1.9
            )
        except asyncio.TimeoutError:
            connected = False
        if not connected:
            return "defer"
        deadline = time.monotonic() + min(90.0, request.get("timeout_ms", 90000) / 1000.0)
        first_send = True
        while time.monotonic() < deadline:
            if not first_send:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not await self._connect(timeout=min(2.0, remaining)):
                    await asyncio.sleep(min(0.25, max(0.0, remaining)))
                    continue
            first_send = False
            active_client = self.client
            try:
                await self._send(request)
            except Exception as error:
                # BlueZ can retain a connected-looking client briefly after a
                # radio hiccup.  Keep the same request alive and reconnect
                # during its remaining approval window instead of immediately
                # falling back to the laptop.
                self.last_error = "BLE write failed: %s" % error
                if active_client is not None:
                    await self._discard_client(active_client)
                await asyncio.sleep(0.1)
                continue
            disconnect_wait = asyncio.create_task(self.disconnect_event.wait())
            remaining = max(0.0, deadline - time.monotonic())
            done, pending = await asyncio.wait(
                (self.current_future, disconnect_wait),
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                if task is not self.current_future:
                    task.cancel()
            if self.current_future in done:
                return self.current_future.result()
            if disconnect_wait in done:
                self.disconnect_event.clear()
                self.client = None
                continue
            return "defer"
        return "defer"

    async def close(self):
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None
        self.connected = False
