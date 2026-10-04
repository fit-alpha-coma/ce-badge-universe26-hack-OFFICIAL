# Computer drivers. They use exactly the same Kart physics as players; the
# only help they get is a capped rubber band (at most 6 % either way).

import math
from config import BOOST, BUG, DUCK, SHIELD, PUSH
from physics import wrap

RUBBER_CAP = 0.06


class Driver:
    def __init__(self, kart, skill, item_rate, rng, drifts=False, care=0.4):
        self.kart = kart
        self.skill = skill
        self.item_rate = item_rate
        self.rng = rng
        self.drifts = drifts
        self.care = care            # how much it slows for corners
        self.lane = rng.uniform(-6, 6)
        self.lane_until = 0.0
        self.hold_item = rng.uniform(0.5, 2.0)
        self.drifting = False
        self.drift_way = 1
        self.time = 0.0

    def control(self, dt, race):
        """Return (steer, brake, drift_held, throttle, use_item)."""
        k = self.kart
        geo = k.geo
        self.time += dt
        if self.time > self.lane_until:
            self.lane = self.rng.uniform(-geo.road * 0.45, geo.road * 0.45)
            self.lane_until = self.time + self.rng.uniform(1.5, 4.0)

        fwd = k.forward_speed()
        fx, fy = math.cos(k.heading), math.sin(k.heading)
        # swerve around karts and bugs just ahead
        for ox, oy in race.obstacles(k):
            dx, dy = ox - k.x, oy - k.y
            ahead = dx * fx + dy * fy
            side = dy * fx - dx * fy
            if 0 < ahead < 22 and abs(side) < 7:
                self.lane = geo.road * 0.6 if side < 0 else -geo.road * 0.6
                self.lane_until = self.time + 1.0
                break

        look = 4 + int(max(0.0, fwd) / 22)
        tx, ty = geo.place(k.idx + look, self.lane)
        diff = wrap(math.atan2(ty - k.y, tx - k.x) - k.heading)
        steer = max(-1.0, min(1.0, diff * 2.4))

        curve = abs(geo.curvature(k.idx + 2, 8))
        corner = 1.0 - min(0.32, max(0.0, curve - 0.6) * self.care)
        gap = race.gap_to_humans(k)   # waypoints ahead (+) or behind (-)
        rubber = max(-RUBBER_CAP, min(RUBBER_CAP, -gap * 0.0015))
        throttle = max(0.5, min(1.0, self.skill * corner * (1.0 + rubber)))

        drift = False
        if self.drifts:
            bend = geo.curvature(k.idx + 2, 14)
            way = 1 if bend > 0 else -1
            if not self.drifting:
                # only on long corners, steering into them, with speed to spare
                if abs(bend) > 1.25 and fwd > 60 and steer * way > 0.5:
                    self.drifting = True
                    self.drift_way = way
            else:
                way = self.drift_way
                overshoot = diff * way < -0.12           # turning past the line
                outside = k.lateral * way < -geo.road * 0.45
                if abs(geo.curvature(k.idx + 1, 6)) < 0.4 or overshoot or outside:
                    self.drifting = False
            drift = self.drifting

        use = False
        if k.item:
            self.hold_item -= dt
            if self.hold_item <= 0 and self.rng.random() < self.item_rate:
                use = self.wants_to_use(race)
                if use:
                    self.hold_item = self.rng.uniform(0.5, 2.0)
        return steer, False, drift, throttle, use

    def wants_to_use(self, race):
        k = self.kart
        item = k.item
        if item in (SHIELD, PUSH):
            return True
        if item == BOOST:
            return abs(k.geo.curvature(k.idx, 10)) < 0.5
        if item == BUG:
            return race.someone_behind(k, 40)
        if item == DUCK:
            return race.someone_ahead(k, 160)
        return False
