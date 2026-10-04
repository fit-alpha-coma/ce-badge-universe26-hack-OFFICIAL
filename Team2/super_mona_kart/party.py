# Party races: badges on the same Wi-Fi race each other.
#
# Every badge simulates only the karts it owns (its player, and the computer
# karts if it is the host) and broadcasts their state about 15 times a second.
# Other karts are drawn from those packets, eased toward a short prediction.
# Items travel as events with ids, and each badge decides whether its own kart
# was hit, so a slow packet never makes you spin from a duck you dodged; when
# a projectile hits someone, every badge removes its copy.
#
# Start: each hello carries the sender's clock, so a badge knows the host's
# clock offset. The host's start message names a countdown start in host time;
# every badge converts it to its own clock, so the race clock (and every finish
# time) is measured from the same moment on all badges.
#
# Packets are untrusted: anything malformed or from a badge outside the race
# is dropped rather than allowed to crash the game.

import random
from config import CHARACTERS, TRACKS, BUG, PUSH
from race import Race, Entrant, HUMAN, CPU, REMOTE, COUNTDOWN_MS
from lights import LOBBY, OFF
from controls import chord
import ui
from ui import W, H, center, panel, prompt

CONNECT, NOWIFI, LOBBY_S, RACING_S = range(4)
BAD_PACKET = (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError)
HELLO_MS = 400
STATE_MS = 66
PEER_TIMEOUT_MS = 3500
RACE_TIMEOUT_MS = 4000      # a racing badge silent this long is out (DNF)
CONNECT_TIMEOUT_MS = 20000
START_DELAY_MS = 2600       # time for the intro card before the countdown
MAX_PLAYERS = 4


class Party:
    def __init__(self, game):
        self.game = game
        self.state = CONNECT
        self.t0 = game.now
        self.id = random.getrandbits(16) | 1
        self.char = game.char
        self.track = 0
        self.peers = {}          # net id -> {"c", "tr", "seen", "off"}
        self.net = None
        self.wlan = None
        self.error = ""
        self.next_hello = 0
        self.next_state = 0
        self.seq = 0
        self.race_id = None
        self.started = set()     # race ids already accepted
        self.owner = {}          # kart index -> net id that simulates it
        self.kart_of = {}        # net id -> kart index of that badge's player
        self.members = set()     # net ids in the current race
        self.remote = {}         # kart index -> (validated state, receive time)
        self.last_seq = {}       # net id -> newest sequence number seen
        self.seen = {}           # net id -> last packet time during the race
        self.addr_of = {}        # net id -> the address it first spoke from
        self.sync = {}           # host id -> (round trip ms, host clock minus ours)
        self.start_local = 0     # local time the countdown starts
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

    def send(self, msg):
        self.seq += 1
        msg["id"] = self.id
        msg["s"] = self.seq
        if self.race_id is not None and msg.get("t") in ("st", "ev"):
            msg["r"] = self.race_id
        self.net.send(msg)

    # -- lobby ---------------------------------------------------------------------

    def players(self):
        """Net ids in the lobby, sorted; the first is the host."""
        now = self.game.now
        for pid in [p for p, d in self.peers.items() if now - d["seen"] > PEER_TIMEOUT_MS]:
            del self.peers[pid]
            if pid not in self.members:
                self.addr_of.pop(pid, None)
        return sorted([self.id] + list(self.peers))[:MAX_PLAYERS]

    def update(self, dt):
        """Lobby screens. Returns "menu" to leave party mode."""
        g = self.game
        a = g.art
        g.backdrop()
        leave = badge.pressed(BUTTON_BACK) or chord()
        if self.state == CONNECT:
            self.poll_connect()
            ui.heading("Party", 10, a, 22)
            dots = "." * (1 + (g.now // 400) % 3)
            center("Joining %s%s" % (self.ssid, dots), 100, a.small, ui.WHITE)
            prompt([("BK/^v", "cancel")], H - 18, a.small)
            return "menu" if leave else None
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
            prompt([("SEL", "back")], H - 18, a.small)
            return "menu" if leave or badge.pressed(BUTTON_SELECT) else None
        self.lobby()
        return "menu" if leave and g.state == g.PARTY_STATE else None

    def lobby(self):
        g = self.game
        a = g.art
        for msg, addr in self.net.receive():
            try:
                if msg.get("t") == "hi":
                    self.parse_hello(msg)   # fully valid before it touches any table
                if self.trusted(msg, addr) and self.handle_lobby(msg):
                    return      # a start message moved us to the race
            except BAD_PACKET:
                pass            # anyone on the network can send junk; drop it
        ids = self.players()
        if g.now >= self.next_hello:
            self.next_hello = g.now + HELLO_MS
            self.send({"t": "hi", "c": self.char, "tr": self.track, "ms": g.now})
            if ids[0] != self.id:
                # measure the host's clock: round trip / 2 is the one-way delay
                self.send({"t": "pg", "to": ids[0], "q": g.now})
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
        center(TRACKS[self.track]["name"], 140, a.small, ui.GOLD)
        if host:
            center("You host (*). Pick a track, start when ready.", 160, a.small, ui.DIM)
            center("%d badge%s connected" % (len(ids), "" if len(ids) == 1 else "s"), 174, a.small, ui.ACCENT)
            prompt([("<>", "racer"), ("^v", "track"), ("SEL", "start"), ("BK/^v", "leave")], H - 18, a.small)
        else:
            center("Waiting for the host to start...", 164, a.small, ui.DIM)
            prompt([("<>", "racer"), ("BK/^v", "leave")], H - 18, a.small)
        if badge.pressed(BUTTON_LEFT):
            self.char = (self.char - 1) % len(CHARACTERS)
        elif badge.pressed(BUTTON_RIGHT):
            self.char = (self.char + 1) % len(CHARACTERS)
        if host:
            held = badge.held()
            both = BUTTON_UP in held and BUTTON_DOWN in held
            if badge.pressed(BUTTON_UP) and not both:
                self.track = (self.track - 1) % len(TRACKS)
            elif badge.pressed(BUTTON_DOWN) and not both:
                self.track = (self.track + 1) % len(TRACKS)
            if badge.pressed(BUTTON_SELECT) and len(ids) >= 2:
                self.host_start(ids)

    def trusted(self, msg, addr):
        """Bind each badge id to the address it first used; drop anything that
        claims that id from elsewhere. There is no keyboard for a shared key,
        so this stops casual spoofing: a forger must also fake the source
        address on the local network."""
        pid = msg["id"]
        if pid == self.id:
            return False
        known = self.addr_of.get(pid)
        if known is None:
            if msg.get("t") != "hi" or len(self.addr_of) >= 4 * MAX_PLAYERS:
                return False    # only a hello introduces a badge
            self.addr_of[pid] = addr
            return True
        return known == addr

    def parse_hello(self, msg):
        c, tr, ms = int(msg["c"]), int(msg["tr"]), int(msg["ms"])
        if not (0 <= c < len(CHARACTERS) and 0 <= tr < len(TRACKS) and 0 <= ms < 1 << 40):
            raise ValueError("bad hello")
        return c, tr, ms

    def handle_lobby(self, msg):
        """Returns True when a start message began a race."""
        pid = msg["id"]
        if pid == self.id:
            return False
        t = msg.get("t")
        now = self.game.now
        if t == "hi":
            c, tr, ms = self.parse_hello(msg)
            if pid not in self.peers and len(self.peers) >= 2 * MAX_PLAYERS:
                return False    # do not let a flood of fake badges grow the table
            self.peers[pid] = {"c": c, "tr": tr, "seen": now, "off": ms - now}
        elif t == "pg" and int(msg["to"]) == self.id:
            self.send({"t": "po", "to": pid, "q": int(msg["q"]), "h": now})
        elif t == "po" and int(msg["to"]) == self.id:
            rtt = now - int(msg["q"])
            if 0 <= rtt < 2000:
                off = int(msg["h"]) + rtt // 2 - now
                best = self.sync.get(pid)
                if best is None or rtt <= best[0]:
                    self.sync[pid] = (rtt, off)
        elif t == "go":
            start = self.check_start(msg)
            # only a host we have heard from can start us, and only into a race
            # whose players are all badges in our lobby
            if start is None or pid not in self.peers or self.id not in start["ids"]:
                return False
            if any(i != self.id and i not in self.peers for i in start["ids"]):
                return False
            if start["race"] not in self.started:
                self.begin(start)
                return True
        return False

    def check_start(self, msg):
        """A validated copy of a start message, or None."""
        ids = [int(i) for i in msg["ids"]]
        chars = [int(c) for c in msg["chars"]]
        cpus = [int(c) for c in msg.get("cpus", ())]
        n = len(CHARACTERS)
        if not 2 <= len(ids) <= MAX_PLAYERS or len(chars) != len(ids) or len(set(ids)) != len(ids):
            return None
        if len(ids) + len(cpus) > MAX_PLAYERS:
            return None
        if any(not 0 <= c < n for c in chars + cpus) or int(msg["id"]) != min(ids):
            return None
        tr = int(msg["tr"])
        if not 0 <= tr < len(TRACKS):
            return None
        return {"id": int(msg["id"]), "ids": ids, "chars": chars, "cpus": cpus, "tr": tr,
                "seed": int(msg["seed"]) & 0xFFFFF, "race": int(msg["race"]), "at": int(msg["at"])}

    def host_start(self, ids):
        chars = [self.char if pid == self.id else self.peers[pid]["c"] for pid in ids]
        used = set(chars)
        cpus = [c for c in range(len(CHARACTERS)) if c not in used][:MAX_PLAYERS - len(ids)]
        msg = {"t": "go", "ids": ids, "chars": chars, "cpus": cpus, "tr": self.track,
               "seed": random.getrandbits(20), "race": random.getrandbits(24),
               "at": self.game.now + START_DELAY_MS}
        for _ in range(3):      # UDP may drop one; repeats carry the same race id
            self.send(dict(msg))
        msg["id"] = self.id
        self.begin(self.check_start(msg))

    # -- race ----------------------------------------------------------------------

    def begin(self, start):
        g = self.game
        ids = start["ids"]
        host = start["id"]
        self.started.add(start["race"])
        self.race_id = start["race"]
        entrants = []
        self.owner = {}
        self.kart_of = {}
        for i, pid in enumerate(ids):
            entrants.append(Entrant(start["chars"][i], HUMAN if pid == self.id else REMOTE))
            self.owner[i] = pid
            self.kart_of[pid] = i
        for c in start["cpus"]:
            entrants.append(Entrant(c, CPU if host == self.id else REMOTE))
            self.owner[len(entrants) - 1] = host
        self.members = set(ids)
        # the countdown starts at host time `at`; convert it to this badge's clock
        if host == self.id:
            offset = 0
        elif host in self.sync:
            offset = self.sync[host][1]      # ping-measured, delay compensated
        else:
            offset = self.peers.get(host, {}).get("off", 0)
        self.start_local = start["at"] - offset
        self.track = start["tr"]
        g.race = Race(TRACKS[self.track], entrants, difficulty=1, seed=start["seed"],
                      grid=list(range(len(entrants))))
        g.me = self.kart_of[self.id]
        self.remote = {}
        self.last_seq = {}
        self.seen = {pid: g.now for pid in ids}
        self.next_state = 0
        self.state = RACING_S
        g.start_party_race(self.track)

    def clock(self):
        """Race time on the shared clock (negative during the countdown)."""
        return self.game.now - self.start_local - COUNTDOWN_MS

    def started_countdown(self):
        return self.game.now >= self.start_local

    def owned(self, kidx):
        return self.owner.get(kidx) == self.id

    def before_step(self, dt):
        g = self.game
        r = g.race
        now = g.now
        for msg, addr in self.net.receive():
            try:
                if self.trusted(msg, addr):
                    self.handle_race(msg, now)
            except BAD_PACKET:
                pass
        # a badge that went quiet leaves the race: its karts are out
        for pid in list(self.members):
            if pid != self.id and now - self.seen.get(pid, now) > RACE_TIMEOUT_MS:
                self.members.discard(pid)
                for kidx, owner in self.owner.items():
                    if owner == pid:
                        k = r.karts[kidx]
                        k.gone = True
                        if k.finished_ms is None:
                            k.dnf = True
                            if kidx not in r.finish_order:
                                r.finish_order.append(kidx)
                r.reorder()
        for kidx, (e, seen) in self.remote.items():
            k = r.karts[kidx]
            if self.owned(kidx) or k.gone:
                continue
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
            if fin is not None and k.finished_ms is None and not k.dnf and kidx not in r.finish_order:
                k.finished_ms = fin
                r.finish_order.append(kidx)
                r.reorder()

    def handle_race(self, msg, now):
        pid = msg["id"]
        if pid == self.id or pid not in self.members:
            return
        if msg.get("r") != self.race_id:
            return                          # a packet from another (older) race
        seq = int(msg["s"])
        self.seen[pid] = now
        t = msg.get("t")
        if t == "st":
            if seq <= self.last_seq.get(pid, -1):
                return                      # reordered: older than what we have
            self.last_seq[pid] = seq
            for e in msg.get("k", ())[:MAX_PLAYERS]:
                state = self.check_state(e, pid)
                if state is not None:
                    self.remote[state[0]] = (state, now)
        elif t == "ev":
            self.apply_event(msg, pid)

    def check_state(self, e, pid):
        """Validate one kart entry; only the badge that owns a kart may move it."""
        if len(e) != 12:
            return None
        r = self.game.race
        kidx = int(e[0])
        if not 0 <= kidx < len(r.karts) or self.owner.get(kidx) != pid:
            return None
        x, y, h, vx, vy = (float(v) for v in e[1:6])
        if not (0 <= x <= 512 and 0 <= y <= 512 and abs(vx) < 400 and abs(vy) < 400 and abs(h) < 10):
            return None
        lap, idx, frac = int(e[6]), int(e[7]), float(e[8])
        if not (-1 <= lap <= r.laps + 1 and 0 <= idx < r.geo.count and 0 <= frac <= 1):
            return None
        flags, item = int(e[9]) & 0x3F, int(e[10])
        if not 0 <= item <= 5:
            return None
        fin = None if e[11] is None else int(e[11])
        if fin is not None and not 0 < fin < 3600000:
            return None
        return (kidx, x, y, h, vx, vy, lap, idx, frac, flags, item, fin)

    def apply_event(self, msg, pid):
        r = self.game.race
        if r is None or r.items is None:
            return
        e = msg.get("e")
        if e == "box":
            r.items.remote_box(int(msg["i"]))
            return
        if e == "hit":
            r.items.consume(int(msg["p"]))
            return
        o = int(msg["o"])
        # only the owner of a kart can fire its items
        if not 0 <= o < len(r.karts) or self.owner.get(o) != pid:
            return
        if e == "bug":
            x, y = float(msg["x"]), float(msg["y"])
            if 0 <= x <= 512 and 0 <= y <= 512 and len(r.items.bugs) < 24:
                r.items.remote_bug(x, y, o, int(msg["p"]))
        elif e == "duck" and len(r.items.ducks) < 12:
            tgt = int(msg.get("g", -1))
            target = r.karts[tgt] if 0 <= tgt < len(r.karts) else None
            r.items.remote_duck(r.karts[o], target, int(msg["p"]))
        elif e == "push":
            pusher = r.rank_of(r.karts[o])
            for i, k in enumerate(r.karts):
                if self.owned(i) and r.rank_of(k) < pusher:
                    k.hit(1.3)

    def after_step(self, dt):
        g = self.game
        r = g.race
        if r.items:
            # spawn data was captured when the item was used, before any step
            for kind, owner, pid, x, y, target in r.items.spawned:
                if not self.owned(owner):
                    continue
                if kind == BUG:
                    self.send({"t": "ev", "e": "bug", "o": owner, "p": pid,
                               "x": round(x, 1), "y": round(y, 1)})
                else:
                    self.send({"t": "ev", "e": "duck", "o": owner, "p": pid, "g": target})
            for name, kid, item in r.events:
                if name == "use" and item == PUSH and kid is not None and self.owned(kid):
                    self.send({"t": "ev", "e": "push", "o": kid})
            for pid in r.items.consumed:
                self.send({"t": "ev", "e": "hit", "p": pid})
            for bi in r.items.picked:
                self.send({"t": "ev", "e": "box", "i": bi})
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
            self.send({"t": "st", "k": ks})

    def back_to_lobby(self):
        self.state = LOBBY_S
        self.remote = {}
        self.race_id = None
        self.game.me = 0
