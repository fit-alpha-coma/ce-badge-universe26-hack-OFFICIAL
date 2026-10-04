# One race: karts, items, laps, standings and events. Plain Python, so a whole
# race can run (and be tested) without a screen.

from rng import Rng
from config import CHARACTERS, DIFFICULTY, POINTS, BOOST
from geom import Geometry
from physics import Kart, collide
from items import Items
from ai import Driver

COUNTDOWN_MS = 3000
GHOST_EVERY_MS = 100
GHOST_MAX = 6000                      # ten minutes of samples at most

COUNTDOWN, RACING, DONE = range(3)

HUMAN, CPU, REMOTE = range(3)


class Entrant:
    def __init__(self, char, kind, name=None):
        self.char = char
        self.kind = kind
        self.name = name or CHARACTERS[char]["name"]


class Race:
    def __init__(self, track, entrants, difficulty=1, seed=None, items=True, laps=None,
                 grid=None, start_boosts=0, record_ghost=False):
        self.track = track
        self.geo = Geometry(track)
        self.laps = laps or track["laps"]
        self.rng = Rng(seed)
        self.entrants = entrants
        diff = DIFFICULTY[difficulty]
        grid = grid or list(range(len(entrants)))
        self.karts = []
        self.drivers = {}
        for i, e in enumerate(entrants):
            ch = CHARACTERS[e.char]
            k = Kart(i, e.char, ch["stats"], self.geo, grid[i])
            k.item = 0
            self.karts.append(k)
            if e.kind == CPU:
                self.drivers[i] = Driver(k, diff["skill"], diff["items"], self.rng,
                                         drifts=difficulty >= 2, care=diff["care"])
        self.items = Items(self.geo, self.rng) if items else None
        self.start_boosts = start_boosts      # time trial: Commit Boosts in hand
        self.phase = COUNTDOWN
        self.clock_ms = -COUNTDOWN_MS         # race time; negative during countdown
        self.events = []
        self.finish_order = []
        self.record_ghost = record_ghost      # time trial only
        self.ghost = []                       # (x, y, heading) samples of kart 0
        self._ghost_next = 0
        self._ranks = {}

    # -- queries -----------------------------------------------------------------

    def humans(self):
        return [k for k in self.karts if self.entrants[k.id].kind != CPU]

    def standings(self):
        def key(k):
            if k.finished_ms is not None:
                return (0, k.finished_ms, 0)
            return (1, 0, -k.progress())
        return sorted(self.karts, key=key)

    def rank_of(self, kart):
        return self._ranks.get(kart.id, 0)

    def gap_to_humans(self, kart):
        hs = [h for h in self.humans() if h is not kart]
        if not hs:
            return 0.0
        best = max(h.progress() for h in hs)
        return kart.progress() - best

    def obstacles(self, kart):
        for k in self.karts:
            if k is not kart and k.fall <= 0:
                yield k.x, k.y
        if self.items:
            for b in self.items.bugs:
                yield b.x, b.y

    def someone_behind(self, kart, dist):
        p = kart.progress() * 6
        return any(0 < p - k.progress() * 6 < dist for k in self.karts if k is not kart)

    def someone_ahead(self, kart, dist):
        p = kart.progress() * 6
        return any(0 < k.progress() * 6 - p < dist for k in self.karts if k is not kart)

    # -- simulation --------------------------------------------------------------

    def step(self, dt, controls, clock=None):
        """Advance dt seconds.

        controls maps kart id -> (steer, brake, drift_held, use_item, assist)
        for human karts; computer karts drive themselves and remote karts are
        moved by the network layer. A party race passes `clock`, the race time
        from a start moment shared by every badge, so finish times compare.
        Events from this step are left in self.events.
        """
        self.events = []
        if self.items:
            self.items.spawned = []
            self.items.consumed = []
        ms = int(dt * 1000) if clock is None else max(0, clock - self.clock_ms)
        if self.phase == COUNTDOWN:
            before = self.clock_ms
            self.clock_ms += ms
            # announce 3, 2, 1 as each second of the countdown begins
            n_before = (-before + 999) // 1000
            n_after = (-self.clock_ms + 999) // 1000
            if before == -COUNTDOWN_MS:
                self.events.append(("count", None, 3))
            elif 0 < n_after < n_before:
                self.events.append(("count", None, n_after))
            if self.clock_ms >= 0:
                self.phase = RACING
                self.clock_ms = 0
                self.events.append(("go", None, None))
                for k in self.karts:
                    if self.entrants[k.id].kind == HUMAN and self.start_boosts:
                        k.item = BOOST  # time trial hands out its boosts one by one
            self._update_ranks()
            return
        self.clock_ms += ms
        now = self.clock_ms
        for k in self.karts:
            kind = self.entrants[k.id].kind
            if kind == REMOTE:
                continue
            if k.gone:
                continue
            if k.finished_ms is not None or k.dnf:
                # cool-down lap: drive gently along the racing line
                d = self.drivers.get(k.id) or self._cooldown_driver(k)
                steer, _b, _d, _t, _u = d.control(dt, self)
                evs = k.drive(dt, steer, False, False, throttle=0.45)
            elif kind == CPU:
                steer, brake, drift, throttle, use = self.drivers[k.id].control(dt, self)
                evs = k.drive(dt, steer, brake, drift, throttle)
                if use and self.items:
                    self.items.use(k, self.karts, self.rank_of, self.events)
            else:
                steer, brake, drift, use, assist = controls.get(k.id, (0.0, False, False, False, False))
                evs = k.drive(dt, steer, brake, drift, 1.0, assist)
                if use and k.item:
                    if self.items:
                        self.items.use(k, self.karts, self.rank_of, self.events)
                    elif self.start_boosts and k.item == BOOST:
                        k.give_boost(1.1)
                        k.item = 0
                        self.start_boosts -= 1
                        self.events.append(("use", k.id, BOOST))
                        if self.start_boosts:
                            k.item = BOOST
            for e in evs:
                self.events.append((e, k.id, None))
        collide([k for k in self.karts if not k.gone])
        for k in self.karts:
            if self.entrants[k.id].kind == REMOTE or k.gone:
                continue
            for e in k.locate(now, dt):
                self.events.append((e, k.id, None))
                if e == "lap" and k.lap > self.laps and k.finished_ms is None and not k.dnf:
                    self.finish(k, now)
                elif e == "lap" and k.lap == self.laps:
                    self.events.append(("final", k.id, None))
        self._update_ranks()
        if self.items:
            # a remote badge decides its own pickups and hits
            local = [k for k in self.karts if self.entrants[k.id].kind != REMOTE and not k.gone]
            self.items.step(dt, local, self.rank_of, self.events)
        k0 = self.karts[0]
        if self.record_ghost and k0.finished_ms is None and now >= self._ghost_next \
                and len(self.ghost) < GHOST_MAX:
            self.ghost.append((round(k0.x, 1), round(k0.y, 1), round(k0.heading, 2)))
            self._ghost_next += GHOST_EVERY_MS
        if self.humans() and all(k.finished_ms is not None or k.dnf for k in self.humans()):
            if self.phase != DONE:
                self.phase = DONE
                self.events.append(("done", None, None))

    def finish(self, kart, now):
        kart.finished_ms = now
        self.finish_order.append(kart.id)
        self.events.append(("finish", kart.id, len(self.finish_order)))

    def _cooldown_driver(self, kart):
        d = Driver(kart, 0.5, 0.0, self.rng)
        self.drivers[kart.id] = d
        return d

    def _update_ranks(self):
        self._ranks = {k.id: i for i, k in enumerate(self.standings())}

    def finalize(self):
        """Freeze the result: karts still racing get a DNF, placed by progress.
        After this nothing can join finish_order twice."""
        for k in self.standings():
            if k.finished_ms is None and k.id not in self.finish_order:
                k.dnf = True
                self.finish_order.append(k.id)
        return self.finish_order

    def results(self):
        """Final order with race times (None for karts still racing)."""
        return [(k.id, k.finished_ms) for k in self.standings()]


def award_points(order, totals):
    """Add Grand Prix points for a finishing order (list of entrant indexes)."""
    for place, idx in enumerate(order):
        if place < len(POINTS):
            totals[idx] = totals.get(idx, 0) + POINTS[place]
    return totals


def finish_unfinished(race):
    """Place karts that had not finished when the humans did, by progress."""
    return race.finalize()
