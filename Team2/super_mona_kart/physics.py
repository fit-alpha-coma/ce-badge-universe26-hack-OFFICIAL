# Kart physics. Plain Python: every kart, human or computer, runs this same
# model, which is the core of keeping races fair.
#
# A kart has a heading and a velocity vector. Speed changes along the heading;
# sideways velocity decays at a rate set by grip, so ice slides and a drift
# carries momentum through the corner.

import math
from geom import ROAD, CURB, OFF, DROP, SIZE

BRAKE = 130.0           # texels/s^2
REVERSE_TOP = 26.0
BOOST_TOP = 1.32        # top speed multiplier while boosting
BOOST_PUSH = 140.0      # extra acceleration while boosting
DRIFT_MIN_SPEED = 44.0
DRIFT_LEVELS = (0.7, 1.4, 2.2)      # seconds of charge for blue, orange, pink
DRIFT_BOOSTS = (0.5, 0.9, 1.3)      # boost seconds awarded per level
SPIN_TIME = 1.1
FALL_TIME = 1.3
OFF_COURSE_RESPAWN = 2.5
MAX_JUMP = 30           # waypoints progress may advance in one step
KART_RADIUS = 3.2
PI2 = math.pi * 2


def wrap(a):
    while a > math.pi:
        a -= PI2
    while a < -math.pi:
        a += PI2
    return a


class Kart:
    def __init__(self, kid, char, stats, geo, slot):
        self.id = kid
        self.char = char
        self.geo = geo
        speed, accel, handling, weight = stats
        self.top = 84.0 + 4.0 * speed
        self.accel = 40.0 + 8.0 * accel
        self.turn = 2.0 + 0.16 * handling
        self.weight = 0.8 + 0.1 * weight
        self.reset(slot)

    def reset(self, slot):
        x, y, h, i = self.geo.grid_slot(slot)
        self.x = x
        self.y = y
        self.heading = h
        self.vx = 0.0
        self.vy = 0.0
        self.idx = i
        self.t = 0.0
        self.lateral = 0.0
        self.lap = 0
        self.surface = ROAD
        self.boost = 0.0
        self.spin = 0.0
        self.shield = 0.0
        self.fall = 0.0
        self.drift = 0          # -1 left, +1 right, 0 not drifting
        self.charge = 0.0
        self.level = 0
        self.hop = 0.0
        self.item = 0
        self.off_course = 0.0
        self.wrong_way = 0.0
        self.finished_ms = None
        self.dnf = False        # did not finish (race finalised or badge left)
        self.gone = False       # a party badge that disconnected: not drawn or hit
        self.lap_start_ms = None
        self.best_lap_ms = None
        self.last_lap_ms = None

    # -- derived -----------------------------------------------------------------

    def forward_speed(self):
        return self.vx * math.cos(self.heading) + self.vy * math.sin(self.heading)

    def progress(self):
        return self.lap * self.geo.count + self.idx + self.t

    # -- effects -----------------------------------------------------------------

    def hit(self, duration=SPIN_TIME):
        """Spin out unless shielded. Returns 'shield', 'spin' or None."""
        if self.fall > 0 or self.finished_ms is not None:
            return None
        if self.shield > 0:
            self.shield = 0.0
            return "shield"
        self.spin = max(self.spin, duration)
        self.drift = 0
        self.charge = 0.0
        self.level = 0
        self.boost = 0.0
        return "spin"

    def give_boost(self, seconds):
        self.boost = max(self.boost, seconds)

    def respawn(self):
        i = self.idx
        self.x, self.y = self.geo.place(i, 0)
        self.heading = self.geo.heading_at(i)
        self.vx = self.vy = 0.0
        self.fall = 0.0
        self.spin = 0.0
        self.off_course = 0.0
        self.lateral = 0.0
        self.surface = ROAD

    # -- simulation --------------------------------------------------------------

    def drive(self, dt, steer, brake, drift_held, throttle=1.0, assist=False):
        """Advance dt seconds. Returns a list of event names."""
        events = []
        geo = self.geo
        if self.fall > 0:
            self.fall -= dt
            if self.fall <= 0:
                self.respawn()
                events.append("respawn")
            return events
        if self.hop > 0:
            self.hop = max(0.0, self.hop - dt)
        if self.spin > 0:
            self.spin = max(0.0, self.spin - dt)
            steer = 0.0
            brake = False
            drift_held = False
            throttle = 0.0
        if self.boost > 0:
            self.boost = max(0.0, self.boost - dt)
        if self.shield > 0:
            self.shield = max(0.0, self.shield - dt)

        surf = self.surface
        grip = geo.spec.get("grip", 1.0)
        top = self.top
        if surf == CURB:
            top *= 0.93
        elif surf == OFF:
            top = min(top, geo.spec.get("off", 40.0))
            grip *= 0.85
        if geo.on_patch(self.x, self.y):
            grip *= 0.45
        if self.boost > 0:
            top *= BOOST_TOP

        h = self.heading
        fx, fy = math.cos(h), math.sin(h)
        fwd = self.vx * fx + self.vy * fy
        lat = -self.vx * fy + self.vy * fx

        # speed along the heading
        if brake:
            if fwd > 0:
                fwd = max(0.0, fwd - BRAKE * dt)
            else:
                fwd = max(-REVERSE_TOP, fwd - 45.0 * dt)
        else:
            target = top * (1.0 if self.boost > 0 else throttle)
            if fwd < target:
                push = self.accel * max(0.12, 1.0 - fwd / target) if target > 0 else 0.0
                if self.boost > 0:
                    push += BOOST_PUSH
                fwd = min(target, fwd + push * dt)
            else:
                # bleed off excess speed (grass, the end of a boost, letting go)
                fwd -= (fwd - target) * (2.8 if surf == OFF else 1.6) * dt

        # drift: start, charge, release
        if self.drift:
            if self.spin > 0 or fwd < DRIFT_MIN_SPEED * 0.7 or surf in (OFF, DROP):
                self.drift = 0
                self.charge = 0.0
                self.level = 0
            elif not drift_held:
                if self.level:
                    self.give_boost(DRIFT_BOOSTS[self.level - 1])
                    events.append("boost")
                self.drift = 0
                self.charge = 0.0
                self.level = 0
            else:
                self.charge += dt * (1.0 + 0.6 * max(0.0, steer * self.drift))
                while self.level < 3 and self.charge >= DRIFT_LEVELS[self.level]:
                    self.level += 1
                    events.append("drift%d" % self.level)
        elif drift_held and abs(steer) > 0.3 and fwd > DRIFT_MIN_SPEED and surf in (ROAD, CURB) \
                and self.spin == 0 and self.hop == 0:
            self.drift = 1 if steer > 0 else -1
            self.charge = 0.0
            self.level = 0
            self.hop = 0.18
            events.append("drift")

        # steering
        speed_factor = min(1.0, abs(fwd) / 22.0)
        if self.drift:
            rate = self.turn * self.drift * (0.9 + 0.55 * steer * self.drift)
        else:
            rate = self.turn * steer
            if assist and steer == 0 and abs(self.lateral) > geo.road * 0.55:
                # nudge back toward the road when nothing is held
                ahead = geo.heading_at(self.idx + 3)
                rate += max(-0.6, min(0.6, wrap(ahead - h) * 1.5))
        if fwd < 0:
            rate = -rate
        if self.spin > 0:
            rate = 9.0  # visual spin; velocity keeps its direction below
        h = wrap(h + rate * speed_factor * dt) if self.spin == 0 else wrap(h + rate * dt)

        # re-project the old velocity onto the new heading; sideways slip decays
        vx = fx * fwd - fy * lat
        vy = fy * fwd + fx * lat
        nfx, nfy = math.cos(h), math.sin(h)
        fwd2 = vx * nfx + vy * nfy
        lat2 = -vx * nfy + vy * nfx
        if self.spin > 0:
            k = 1.5
            fwd2 *= math.exp(-2.5 * dt)
        elif self.drift:
            k = 4.5 * grip
        else:
            k = 12.0 * grip
        lat2 *= math.exp(-k * dt)
        self.heading = h
        self.vx = nfx * fwd2 - nfy * lat2
        self.vy = nfy * fwd2 + nfx * lat2

        self.x += self.vx * dt
        self.y += self.vy * dt
        lo, hi = 6.0, SIZE - 6.0
        if self.x < lo or self.x > hi:
            self.x = lo if self.x < lo else hi
            self.vx = -self.vx * 0.3
        if self.y < lo or self.y > hi:
            self.y = lo if self.y < lo else hi
            self.vy = -self.vy * 0.3

        if geo.on_pad(self.x, self.y) and self.boost < 0.5 and self.spin == 0:
            self.give_boost(0.8)
            events.append("pad")
        return events

    def locate(self, now_ms, dt):
        """Track position, surface, laps. Returns a list of event names."""
        events = []
        if self.fall > 0:
            return events
        geo = self.geo
        n = geo.count
        old = self.idx
        idx, t, lateral = geo.nearest(self.x, self.y, old)
        far = abs(lateral) > geo.road + geo.curb + 24
        if far:
            # lost the local search: look everywhere, but only accept a small
            # move along the lap, so cutting across the infield gains nothing
            gi = geo.nearest_global(self.x, self.y)
            gidx, gt, glat = geo.nearest(self.x, self.y, gi)
            jump = (gidx - old) % n
            if jump <= MAX_JUMP or jump >= n - MAX_JUMP:
                idx, t, lateral = gidx, gt, glat
                far = abs(lateral) > geo.road + geo.curb + 24
        if far:
            self.off_course += dt
            self.lateral = lateral
            if self.off_course > OFF_COURSE_RESPAWN:
                self.respawn()
                events.append("respawn")
            return events
        self.off_course = 0.0
        self.idx, self.t, self.lateral = idx, t, lateral
        self.surface = geo.surface(lateral)
        if self.surface == DROP and self.fall <= 0:
            self.fall = FALL_TIME
            self.vx = self.vy = 0.0
            self.drift = 0
            self.charge = 0.0
            self.level = 0
            events.append("fall")
        # wrong way: driving against the track for a while
        fwd = self.forward_speed()
        d = math.cos(self.heading - geo.heading_at(idx))
        if abs(fwd) > 15 and d * (1 if fwd > 0 else -1) < -0.3:
            self.wrong_way += dt
        else:
            self.wrong_way = 0.0
        if old > n * 3 // 4 and idx < n // 4:
            self.lap += 1
            if self.lap_start_ms is not None:
                lap_ms = now_ms - self.lap_start_ms
                self.last_lap_ms = lap_ms
                if self.best_lap_ms is None or lap_ms < self.best_lap_ms:
                    self.best_lap_ms = lap_ms
            self.lap_start_ms = now_ms
            events.append("lap")
        elif old < n // 4 and idx > n * 3 // 4:
            self.lap -= 1
            # reversing over the line voids the current lap's timing
            self.lap_start_ms = None
        return events


def collide(karts):
    """Push overlapping karts apart by weight; the one driving in loses speed."""
    n = len(karts)
    lim = KART_RADIUS * 2
    for i in range(n):
        a = karts[i]
        if a.fall > 0 or a.gone:
            continue
        for j in range(i + 1, n):
            b = karts[j]
            if b.fall > 0 or b.gone:
                continue
            dx = b.x - a.x
            dy = b.y - a.y
            d2 = dx * dx + dy * dy
            if d2 >= lim * lim or d2 < 1e-6:
                continue
            d = math.sqrt(d2)
            overlap = lim - d
            wa = b.weight / (a.weight + b.weight)
            wb = 1.0 - wa
            nx, ny = dx / d, dy / d
            a.x -= nx * overlap * wa
            a.y -= ny * overlap * wa
            b.x += nx * overlap * wb
            b.y += ny * overlap * wb
            ca = a.vx * nx + a.vy * ny
            cb = b.vx * nx + b.vy * ny
            rel = ca - cb
            if rel > 0:
                # exchange part of the closing velocity, heavier karts give less
                imp = rel * 0.7
                a.vx -= nx * imp * wa
                a.vy -= ny * imp * wa
                b.vx += nx * imp * wb
                b.vy += ny * imp * wb
