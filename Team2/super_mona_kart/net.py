# UDP transport for party races. On a badge every packet is broadcast on the
# local network; in the simulator (secrets.SIM_BADGE set) badges are ports on
# 127.0.0.1. Messages are small JSON objects; this module only moves them.

import json
import socket

PORT = 47311
VERSION = 1


def encode(msg):
    return json.dumps(msg).encode()


def decode(data):
    try:
        msg = json.loads(data)
    except (ValueError, TypeError):
        return None
    if not isinstance(msg, dict) or msg.get("v") != VERSION or not isinstance(msg.get("id"), int):
        return None
    return msg


class Net:
    def __init__(self, sim_badge=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except (OSError, AttributeError):
            pass
        if sim_badge is None:
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except (OSError, AttributeError):
                pass
            self.sock.bind(socket.getaddrinfo("0.0.0.0", PORT)[0][-1])
            self.targets = [socket.getaddrinfo("255.255.255.255", PORT)[0][-1]]
        else:
            self.sock.bind(socket.getaddrinfo("127.0.0.1", PORT + sim_badge)[0][-1])
            self.targets = [socket.getaddrinfo("127.0.0.1", PORT + i)[0][-1]
                            for i in range(4) if i != sim_badge]
        self.sock.setblocking(False)
        self.sent = 0
        self.errors = 0

    def send(self, msg):
        msg["v"] = VERSION
        data = encode(msg)
        for t in self.targets:
            try:
                self.sock.sendto(data, t)
                self.sent += 1
            except OSError:
                self.errors += 1

    def receive(self, limit=32):
        out = []
        for _ in range(limit):
            try:
                data, _addr = self.sock.recvfrom(1024)
            except OSError:
                break
            msg = decode(data)
            if msg is not None:
                out.append(msg)
        return out

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
