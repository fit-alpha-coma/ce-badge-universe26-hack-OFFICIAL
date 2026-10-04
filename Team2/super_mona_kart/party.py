# Party races: badges on the same Wi-Fi race each other.
#
# Every badge simulates only the karts it owns (its player, and the computer
# karts if it is the host) and broadcasts their state about 15 times a second.
# Other karts are drawn from those packets, eased toward a short prediction.
# Items travel as events, and each badge decides whether its own kart was hit,
# so a slow packet can never make you spin from a duck you dodged.

import math
import random
from config import CHARACTERS, TRACKS, BUG, DUCK, PUSH
from race import Race, Entrant, HUMAN, CPU, REMOTE
from lights import LOBBY, OFF
import ui
from ui import W, H, center, text, panel, prompt

CONNECT, NOWIFI, LOBBY_S, RACING_S = range(4)
HELLO_MS = 400
STATE_MS = 66
PEER_TIMEOUT_MS = 3500
CONNECT_TIMEOUT_MS = 20000
MAX_PLAYERS = 4


class Party:
    def __init__(self, game):
        self.game = game
        self.state = CONNECT
        self.t0 = game.now
        self.id = random.getrandbits(16) | 1
        self.char = game.char
        self.track = 0
        self.peers = {}          # net id -> {"c": char, "seen": ms, "tr": track}
        self.net = None
        self.wlan = None
        self.error = ""
        self.next_hello = 0
        self.next_state = 0
        self.owner = {}          # kart index -> net id that simulates it
        self.kart_of = {}        # net id -> kart index of that badge's player
        self.remote = {}         # kart index -> latest packet fields
        self.host_id = None
        try:
            import secrets
            self.ssid = getattr(secrets, "WIFI_SSID", "") or ""
            self.psk = getattr(secrets, "WIFI_PASSWORD", "") or ""
            self.sim = getattr(secrets, "SIM_BADGE", None)
        except ImportError:
            self.ssid, self.psk, self.sim = "", "", None
        if not self.ssid:
            self.fail("No Wi-Fi details on this badge.")
        else:
            self.connect()

    # -- connection ----------------------------------------------------------------

    def fail(self, msg):
        self.state = NOWIFI
        self.error = msg

    def connect(self):
        # network.WLAN directly: the firmware's wifi.connect() resets the badge
        # on a bad password or a timeout, which would be a rude way to leave.
        try:
            import network
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(True)
            if not self.wlan.isconnected():
                self.wlan.connect(self.ssid, self.psk)
        except (OSError, ImportError) as e:
            self.fail("Wi-Fi error: %s" % e)

    def poll_connect(self):
        if self.wlan.isconnected():
            try:
                from net import Net
                self.net = Net(self.sim)
            except OSError as e:
                self.fail("Network error: %s" % e)
                return
            self.state = LOBBY_S
            return
        status = self.wlan.status() if hasattr(self.wlan, "status") else 1
        if status in (-1, -2, -3) or self.game.now - self.t0 > CONNECT_TIMEOUT_MS:
            self.fail("Could not join %s." % self.ssid)

    def close(self):
        if self.net:
            self.net.close()
            self.net = None
        self.game.lights.set(OFF)

    # -- lobby ---------------------------------------------------------------------

    def players(self):
        """Net ids in the lobby, sorted; the first is the host."""
        now = self.game.now
        for pid in [p for p, d in self.peers.items() if now - d["seen"] > PEER_TIMEOUT_MS]:
            del self.peers[pid]
        ids = sorted([self.id] + list(self.peers))
        return ids[:MAX_PLAYERS]

    def is_host(self):
        return self.players()[0] == self.id

    def update(self, dt):
        g = self.game
        a = g.art
        g.backdrop()
        if self.state == CONNECT:
            self.poll_connect()
            ui.heading("Party", 10, a, 22)
            dots = "." * (1 + (g.now // 400) % 3)
            center("Joining %s%s" % (self.ssid, dots), 100, a.small, ui.WHITE)
            prompt([("BK", "cancel")], H - 18, a.small)
            if badge.pressed(BUTTON_BACK):
                return "menu"
            return None
        if self.state == NOWIFI:
            ui.heading("Party", 10, a, 22)
            panel(20, 50, W - 40, 140)
            center(self.error, 60, a.small, color.rgb(255, 160, 140))
            lines = ("Put the badge in disk mode (double-tap RESET)",
                     "and set WIFI_SSID / WIFI_PASSWORD in secrets.py.",
                     "Conference Wi-Fi often blocks badge-to-badge",
                     "traffic: a phone hotspot works best.")
            for i, line in enumerate(lines):
                center(line, 90 + i * 16, a.small, ui.DIM)
            prompt([("BK", "back")], H - 18, a.small)
            if badge.pressed(BUTTON_BACK) or badge.pressed(BUTTON_SELECT):
                return "menu"
            return None
        self.lobby(dt)
        if badge.pressed(BUTTON_BACK):
            return "menu"
        return None

    def lobby(self, dt):
        g = self.game
        a = g.art
        for msg in self.net.receive():
            self.handle_lobby(msg)
        if g.state != g.PARTY_STATE:
            return      # a start message moved us to the race
        if g.now >= self.next_hello:
            self.next_hello = g.now + HELLO_MS
            self.net.send({"t": "hi", "id": self.id, "c": self.char, "tr": self.track})
        ids = self.players()
        host = ids[0] == self.id
        if not host:
            self.track = self.peers[ids[0]].get("tr", self.track)
        g.lights.set(LOBBY, len(ids))
        ui.heading("Party lobby", 6, a, 20)
        for slot in range(MAX_PLAYERS):
            x = 14 + slot * 74
            panel(x, 40, 68, 84)
            if slot < len(ids):
                pid = ids[slot]
                ch = self.char if pid == self.id else self.peers[pid]["c"]
                screen.blit(a.karts[ch][3], rect(x + 2, 44, 64, 64))
                tag = ("YOU" if pid == self.id else CHARACTERS[ch]["name"]) + (" *" if slot == 0 else "")
                center(tag, 108, a.small, ui.GOLD if pid == self.id else ui.WHITE, x0=x, x1=x + 68)
            else:
                center("CPU", 74, a.small, ui.DIM, x0=x, x1=x + 68)
        panel(14, 132, W - 28, 60)
        tr = TRACKS[self.track]
        center(tr["name"], 140, a.small, ui.GOLD)
        if host:
            center("You host (*). Pick a track, start when ready.", 160, a.small, ui.DIM)
            center("%d badge%s connected" % (len(ids), "" if len(ids) == 1 else "s"), 174, a.small, ui.ACCENT)
            prompt([("<>", "racer"), ("^v", "track"), ("SEL", "start"), ("BK", "leave")], H - 18, a.small)
        else:
            center("Waiting for the host to start...", 164, a.small, ui.DIM)
            prompt([("<>", "racer"), ("BK", "leave")], H - 18, a.small)
        if badge.pressed(BUTTON_LEFT):
            self.char = (self.char - 1) % len(CHARACTERS)
        elif badge.pressed(BUTTON_RIGHT):
            self.char = (self.char + 1) % len(CHARACTERS)
        if host:
            if badge.pressed(BUTTON_UP):
                self.track = (self.track - 1) % len(TRACKS)
            elif badge.pressed(BUTTON_DOWN):
                self.track = (self.track + 1) % len(TRACKS)
            if badge.pressed(BUTTON_SELECT) and len(ids) >= 2:
                self.host_start(ids)

    def handle_lobby(self, msg):
        pid = msg["id"]
        if pid == self.id:
            return
        t = msg.get("t")
        if t == "hi":
            d = self.peers.setdefault(pid, {})
            d["c"] = int(msg.get("c", 0)) % len(CHARACTERS)
            d["tr"] = int(msg.get("tr", 0)) % len(TRACKS)
            d["seen"] = self.game.now
        elif t == "go" and self.id in msg.get("ids", ()):
            self.begin(msg)

    def host_start(self, ids):
        chars = [self.char if pid == self.id else self.peers[pid]["c"] for pid in ids]
        used = set(chars)
        cpus = [c for c in range(len(CHARACTERS)) if c not in used][:MAX_PLAYERS - len(ids)]
        msg = {"t": "go", "id": self.id, "ids": ids, "chars": chars, "cpus": cpus,
               "tr": self.track, "seed": random.getrandbits(20)}
        for _ in range(3):      # UDP may drop one; repeats are ignored
            self.net.send(dict(msg))
        self.begin(msg)

    # -- race ----------------------------------------------------------------------

    def begin(self, msg):
        g = self.game
        ids = msg["ids"]
        chars = msg["chars"]
        cpus = msg.get("cpus", [])
        host = msg["id"]
        self.host_id = host
        entrants = []
        self.owner = {}
        self.kart_of = {}
        for i, pid in enumerate(ids):
            entrants.append(Entrant(chars[i], HUMAN if pid == self.id else REMOTE))
            self.owner[i] = pid
            self.kart_of[pid] = i
        for c in cpus:
            entrants.append(Entrant(c, CPU if host == self.id else REMOTE))
            self.owner[len(entrants) - 1] = host
        self.track = msg["tr"]
        spec = TRACKS[self.track]
        g.race = Race(spec, entrants, difficulty=1, seed=msg["seed"], grid=list(range(len(entrants))))
        g.me = self.kart_of[self.id]
        self.remote = {}
        self.next_state = 0
        self.state = RACING_S
        g.start_party_race(self.track)

    def owned(self, kidx):
        return self.owner.get(kidx) == self.id

    def before_step(self, dt):
        g = self.game
        r = g.race
        now = g.now
        for msg in self.net.receive():
            pid = msg["id"]
            if pid == self.id:
                continue
            t = msg.get("t")
            if pid in self.peers:
                self.peers[pid]["seen"] = now
            if t == "st":
                for e in msg.get("k", ()):
                    if len(e) == 12:
                        self.remote[int(e[0])] = (e, now)
            elif t == "ev":
                self.apply_event(msg)
        for kidx, (e, seen) in self.remote.items():
            if kidx >= len(r.karts) or self.owned(kidx):
                continue
            k = r.karts[kidx]
            _i, x, y, h, vx, vy, lap, idx, frac, flags, item, fin = e
            age = min(0.25, (now - seen) / 1000.0)
            px, py = x + vx * age, y + vy * age
            k.x += (px - k.x) * 0.5
            k.y += (py - k.y) * 0.5
            k.heading = h
            k.vx, k.vy = vx, vy
            k.lap, k.idx, k.t = lap, idx, frac
            k.spin = 0.5 if flags & 1 else 0.0
            k.boost = 0.5 if flags & 2 else 0.0
            k.shield = 1.0 if flags & 4 else 0.0
            k.fall = 0.5 if flags & 8 else 0.0
            k.level = (flags >> 4) & 3
            k.drift = 1 if k.level else 0
            k.item = item
            if fin is not None and k.finished_ms is None:
                k.finished_ms = fin
                r.finish_order.append(kidx)
                r.finish_order.sort(key=lambda i: r.karts[i].finished_ms)

    def apply_event(self, msg):
        r = self.game.race
        if r is None or r.items is None:
            return
        e = msg.get("e")
        o = int(msg.get("o", -1))
        if not 0 <= o < len(r.karts):
            return
        if e == "bug":
            r.items.remote_bug(float(msg["x"]), float(msg["y"]), o)
        elif e == "duck":
            tgt = int(msg.get("g", -1))
            target = r.karts[tgt] if 0 <= tgt < len(r.karts) else None
            r.items.remote_duck(r.karts[o], target)
        elif e == "push":
            pusher = r.rank_of(r.karts[o])
            for i, k in enumerate(r.karts):
                if self.owned(i) and r.rank_of(k) < pusher:
                    k.hit(1.3)
        elif e == "box":
            r.items.remote_box(int(msg.get("i", -1)))

    def after_step(self, dt):
        g = self.game
        r = g.race
        if r.items:
            for name, kid, item in r.events:
                if name != "use" or kid is None or not self.owned(kid):
                    continue
                if item == BUG and r.items.bugs:
                    b = r.items.bugs[-1]
                    self.net.send({"t": "ev", "id": self.id, "e": "bug", "o": kid,
                                   "x": round(b.x, 1), "y": round(b.y, 1)})
                elif item == DUCK and r.items.ducks:
                    d = r.items.ducks[-1]
                    tgt = d.target.id if d.target is not None else -1
                    self.net.send({"t": "ev", "id": self.id, "e": "duck", "o": kid, "g": tgt})
                elif item == PUSH:
                    self.net.send({"t": "ev", "id": self.id, "e": "push", "o": kid})
            for bi in r.items.picked:
                self.net.send({"t": "ev", "id": self.id, "e": "box", "o": 0, "i": bi})
        if g.now >= self.next_state:
            self.next_state = g.now + STATE_MS
            ks = []
            for i, k in enumerate(r.karts):
                if not self.owned(i):
                    continue
                flags = (1 if k.spin > 0 else 0) | (2 if k.boost > 0 else 0) | \
                        (4 if k.shield > 0 else 0) | (8 if k.fall > 0 else 0) | ((k.level & 3) << 4)
                ks.append([i, round(k.x, 1), round(k.y, 1), round(k.heading, 3), round(k.vx, 1),
                           round(k.vy, 1), k.lap, k.idx, round(k.t, 2), flags, k.item, k.finished_ms])
            self.net.send({"t": "st", "id": self.id, "k": ks})

    def back_to_lobby(self):
        self.state = LOBBY_S
        self.remote = {}
        self.game.me = 0
