"""Authenticated loopback IPC between permission hooks and the BLE daemon."""

import asyncio
import json
import socket


MAX_IPC_LINE = 128 * 1024


def request_sync(config, operation, payload=None, timeout=92.0):
    message = {
        "token": config["ipc_token"],
        "op": operation,
        "payload": payload,
    }
    encoded = json.dumps(message, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(encoded) > MAX_IPC_LINE:
        raise RuntimeError("IPC request is too large")
    with socket.create_connection(
        (config.get("ipc_host", "127.0.0.1"), int(config.get("ipc_port", 47653))),
        timeout=min(timeout, 2.0),
    ) as connection:
        connection.settimeout(timeout)
        connection.sendall(encoded)
        response = bytearray()
        while len(response) <= MAX_IPC_LINE:
            part = connection.recv(4096)
            if not part:
                break
            response.extend(part)
            if b"\n" in part:
                break
    if not response:
        raise RuntimeError("Pager daemon closed the connection")
    try:
        value = json.loads(bytes(response).split(b"\n", 1)[0].decode("utf-8"))
    except (ValueError, UnicodeError) as error:
        raise RuntimeError("Pager daemon returned invalid data") from error
    if not value.get("ok"):
        raise RuntimeError(value.get("error") or "Pager daemon request failed")
    return value


async def _reply(writer, value):
    writer.write(json.dumps(value, separators=(",", ":")).encode("utf-8") + b"\n")
    await writer.drain()


async def handle_client(reader, writer, bridge, config):
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=2.0)
        if len(raw) > MAX_IPC_LINE:
            raise RuntimeError("IPC request is too large")
        message = json.loads(raw.decode("utf-8"))
        if message.get("token") != config["ipc_token"]:
            await _reply(writer, {"ok": False, "error": "authentication failed"})
            return
        operation = message.get("op")
        if operation in ("request", "demo"):
            payload = message.get("payload")
            if not isinstance(payload, dict):
                raise RuntimeError("request payload must be an object")
            decision = await bridge.submit(payload)
            await _reply(writer, {"ok": True, "decision": decision})
        elif operation == "status":
            await _reply(writer, {"ok": True, "status": bridge.status()})
        else:
            await _reply(writer, {"ok": False, "error": "unknown operation"})
    except (asyncio.TimeoutError, ValueError, UnicodeError, RuntimeError) as error:
        try:
            await _reply(writer, {"ok": False, "error": str(error)})
        except (ConnectionError, OSError):
            pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass


async def run_server(bridge, config):
    server = await asyncio.start_server(
        lambda reader, writer: handle_client(reader, writer, bridge, config),
        config.get("ipc_host", "127.0.0.1"),
        int(config.get("ipc_port", 47653)),
        limit=MAX_IPC_LINE,
    )
    worker = asyncio.create_task(bridge.run(), name="copilot-pager-ble")
    try:
        async with server:
            await server.serve_forever()
    finally:
        worker.cancel()
        await bridge.close()

