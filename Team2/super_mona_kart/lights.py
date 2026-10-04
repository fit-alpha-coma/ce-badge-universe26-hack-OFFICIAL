# The four case lights (CL0..CL3), used sparingly: a base pattern plus short
# flashes layered on top. Writes go to badge.caselights() only when a value
# changes, and everything turns off when the setting is off or the app exits.

import math

OFF, COUNTDOWN, DRIFT, FINAL, CHASE, LOBBY = range(6)


class Lights:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.base = OFF
        self.arg = 0
        self.flash_until = 0
        self.flash_kind = None
        self.flash_start = 0
        self._last = None

    def set(self, base, arg=0):
        self.base = base
        self.arg = arg

    def flash(self, kind, now, ms):
        self.flash_kind = kind
        self.flash_start = now
        self.flash_until = now + ms

    def values(self, now):
        """The four duty values (0..1) for this moment. Pure, so it is testable."""
        if not self.enabled:
            return (0.0, 0.0, 0.0, 0.0)
        if now < self.flash_until:
            t = now - self.flash_start
            if self.flash_kind == "boost":
                v = 1.0 - t / max(1, self.flash_until - self.flash_start)
                return (v, v, v, v)
            if self.flash_kind == "hit":
                on = (t // 90) % 2 == 0
                return (0.8, 0.8, 0.8, 0.8) if on else (0.0, 0.0, 0.0, 0.0)
            if self.flash_kind == "item":
                v = 0.5 * (1.0 - t / max(1, self.flash_until - self.flash_start))
                return (v, v, v, v)
            if self.flash_kind == "go":
                return (1.0, 1.0, 1.0, 1.0)
        b = self.base
        if b == COUNTDOWN:
            # one more light for each count: 3 -> one lit, 2 -> two, 1 -> three
            lit = 4 - self.arg
            return tuple(0.55 if i < lit else 0.0 for i in range(4))
        if b == DRIFT:
            v = (0.0, 0.15, 0.3, 0.5)[min(3, self.arg)]
            return (v, v, v, v)
        if b == FINAL:
            v = 0.12 + 0.12 * math.sin(now / 300.0)
            return (v, v, v, v)
        if b == CHASE:
            i = (now // 110) % 4
            return tuple(0.9 if j == i else 0.08 for j in range(4))
        if b == LOBBY:
            return tuple(0.35 if j < self.arg else 0.0 for j in range(4))
        return (0.0, 0.0, 0.0, 0.0)

    def update(self, now):
        v = self.values(now)
        q = tuple(int(x * 50) for x in v)
        if q != self._last:
            self._last = q
            badge.caselights(*v)

    def off(self):
        self._last = None
        self.base = OFF
        self.flash_until = 0
        badge.caselights(0)
