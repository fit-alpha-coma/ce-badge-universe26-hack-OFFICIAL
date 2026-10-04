# Kart physics, lap counting and the computer drivers.

import math
import random
from track import ROAD, CURB, SIZE

TOP_SPEED = 92.0        # texels per second on tarmac
GRASS_SPEED = 38.0      # top speed off the road
ACCEL = 60.0
BRAKE = 120.0
DRAG = 0.35             # fraction of speed lost per second when coasting
TURN = 2.5              # radians per second at full lock and speed
KART_RADIUS = 3.0
PI2 = math.pi * 2


def wrap_angle(a):
    while a > math.pi:
        a -= PI2
    while a < -math.pi:
        a += PI2
    return a


class Kart:
    def __init__(self, name, views, track, slot):
        self.name = name
        self.views = views
        self.track = track
        self.reset(slot)

    def reset(self, slot):
        """Place the kart on the starting grid. Slot 0 is pole position."""
        track = self.track
        idx = (-2 - (slot // 2) * 3) % track.count
        h = track.heading_at(idx)
        px, py = track.points[idx]
        side = -7 if slot % 2 == 0 else 7
        self.x = px - math.sin(h) * side
        self.y = py + math.cos(h) * side
        self.heading = h
        self.speed = 0.0
        self.idx = idx
        self.t = 0.0
        self.lap = 0
        self.offroad = False
        self.finished_ms = None
        self.lap_start_ms = None
        self.best_lap_ms = None

    def progress(self):
        return self.lap * self.track.count + self.idx + self.t

    def drive(self, dt, steer, throttle, brake):
        """Advance the physics. steer is -1..1, throttle and brake 0..1."""
        top = GRASS_SPEED if self.offroad else TOP_SPEED
        v = self.speed
        if brake:
            v -= BRAKE * brake * dt
        elif throttle:
            # approach throttle * top; the curve flattens near the target
            target = top * throttle
            if v < target:
                v += ACCEL * (target - v) / top * dt * 2
        else:
            v -= v * DRAG * dt
        if v > top:
            v -= (v - top) * 2.5 * dt
        if v < 0:
            v = 0.0
        self.speed = v
        grip = v / 30.0
        self.heading = wrap_angle(self.heading + steer * TURN * dt * (grip if grip < 1 else 1))
        self.x += math.cos(self.heading) * v * dt
        self.y += math.sin(self.heading) * v * dt
        lim = SIZE - 4
        self.x = 4 if self.x < 4 else (lim if self.x > lim else self.x)
        self.y = 4 if self.y < 4 else (lim if self.y > lim else self.y)

    def locate(self, now_ms):
        """Update waypoint, off-road state and laps. Returns True on a new lap."""
        n = self.track.count
        old = self.idx
        self.idx, self.t, dist = self.track.nearest(self.x, self.y, self.idx)
        self.offroad = dist > ROAD + CURB * 0.5
        if old > n * 3 // 4 and self.idx < n // 4:
            self.lap += 1
            if self.lap_start_ms is not None:
                lap_ms = now_ms - self.lap_start_ms
                if self.best_lap_ms is None or lap_ms < self.best_lap_ms:
                    self.best_lap_ms = lap_ms
            self.lap_start_ms = now_ms
            return True
        if old < n // 4 and self.idx > n * 3 // 4:
            self.lap -= 1
        return False


class Driver:
    """Steers a kart along the racing line with its own skill and wobble."""

    def __init__(self, kart, skill):
        self.kart = kart
        self.skill = skill
        self.lane = random.uniform(-6, 6)
        self.next_lane_ms = 0

    def control(self, now_ms, leader_gap, karts):
        k = self.kart
        track = k.track
        if now_ms > self.next_lane_ms:
            self.lane = random.uniform(-7, 7)
            self.next_lane_ms = now_ms + random.randint(1500, 4000)
        # pull out to overtake a kart just ahead in the same lane
        fx = math.cos(k.heading)
        fy = math.sin(k.heading)
        for o in karts:
            if o is k:
                continue
            dx = o.x - k.x
            dy = o.y - k.y
            ahead = dx * fx + dy * fy
            side = dy * fx - dx * fy
            if 0 < ahead < 16 and abs(side) < 6:
                self.lane = 8 if side < 0 else -8
                self.next_lane_ms = now_ms + 1200
                break
        ahead = (k.idx + 4) % track.count
        h = track.heading_at(ahead)
        px, py = track.points[ahead]
        tx = px - math.sin(h) * self.lane
        ty = py + math.cos(h) * self.lane
        want = math.atan2(ty - k.y, tx - k.x)
        diff = wrap_angle(want - k.heading)
        steer = diff * 2.2
        steer = -1.0 if steer < -1 else (1.0 if steer > 1 else steer)
        # rubber band: ease off when far ahead of the player, push when behind
        throttle = self.skill - leader_gap * 0.004
        throttle = 0.55 if throttle < 0.55 else (1.0 if throttle > 1.0 else throttle)
        brake = 0.4 if abs(diff) > 1.0 and k.speed > 50 else 0
        return steer, throttle, brake


def bump(karts):
    """Push overlapping karts apart and trade a little speed."""
    n = len(karts)
    for i in range(n):
        a = karts[i]
        for j in range(i + 1, n):
            b = karts[j]
            dx = b.x - a.x
            dy = b.y - a.y
            d2 = dx * dx + dy * dy
            lim = KART_RADIUS * 2
            if d2 < lim * lim and d2 > 0.0001:
                d = math.sqrt(d2)
                push = (lim - d) * 0.5 / d
                a.x -= dx * push
                a.y -= dy * push
                b.x += dx * push
                b.y += dy * push
                # only the kart driving into the other one loses speed
                closing_a = (math.cos(a.heading) * dx + math.sin(a.heading) * dy) / d
                closing_b = -(math.cos(b.heading) * dx + math.sin(b.heading) * dy) / d
                rel = closing_a * a.speed - closing_b * b.speed
                if rel > 3:
                    a.speed *= 0.88
                elif rel < -3:
                    b.speed *= 0.88
