# Track geometry. Plain Python with no badge globals, so it runs (and is
# tested) on a desktop too.
#
# A track is a closed loop of control points in texel space. It is smoothed
# with a Catmull-Rom spline and resampled to evenly spaced waypoints, so a
# waypoint index measures distance along the lap.

import math

SIZE = 512          # the track texture is SIZE x SIZE texels; 1 texel = 1 world unit
SCALE = 2           # layouts are drawn on a 256 grid and scaled up to SIZE
STEP = 6.0          # spacing between waypoints

# surfaces, from best to worst grip
ROAD = 0
CURB = 1
OFF = 2             # grass, sand or snow, depending on the track
DROP = 3            # lava: the kart falls in and is put back


def _catmull(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    out = []
    for k in (0, 1):
        a, b, c, d = p0[k], p1[k], p2[k], p3[k]
        out.append(0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t2
                          + (3 * b - a - 3 * c + d) * t3))
    return out[0], out[1]


def smooth(layout, step=STEP):
    n = len(layout)
    dense = []
    for i in range(n):
        p0, p1, p2, p3 = layout[i - 1], layout[i], layout[(i + 1) % n], layout[(i + 2) % n]
        for k in range(20):
            dense.append(_catmull(p0, p1, p2, p3, k / 20))
    out = [dense[0]]
    carry = 0.0
    m = len(dense)
    for i in range(1, m + 1):
        a, b = dense[i - 1], dense[i % m]
        seg = math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
        d = step - carry
        while d <= seg:
            t = d / seg
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            d += step
        carry = seg - (d - step)
    # drop a last point that sits on top of the first
    if math.sqrt((out[-1][0] - out[0][0]) ** 2 + (out[-1][1] - out[0][1]) ** 2) < step / 2:
        out.pop()
    return out


class Geometry:
    def __init__(self, spec):
        self.spec = spec
        self.road = spec["road"]
        self.curb = spec["curb"]
        self.drop = spec.get("drop", False)
        self.points = smooth([(x * SCALE, y * SCALE) for x, y in spec["layout"]])
        self.count = len(self.points)
        self.length = self.count * STEP
        n = self.count
        pts = self.points
        self.headings = []
        for i in range(n):
            a = pts[i]
            b = pts[(i + 1) % n]
            self.headings.append(math.atan2(b[1] - a[1], b[0] - a[0]))
        # boost pads and patches are placed by waypoint index and lateral offset
        # pads, patches and item boxes are placed by fraction of the lap
        self.pads = []
        for f, lat in spec.get("pads", ()):
            i = int(f * n)
            self.pads.append(self.place(i, lat) + (self.headings[i],))
        self.patches = [self.place(int(f * n), lat) + (r,) for f, lat, r in spec.get("patches", ())]
        self.box_rows = [int(f * n) for f in spec.get("boxes", ())]

    def place(self, i, lateral):
        """World position `lateral` texels right of waypoint i."""
        i %= self.count
        h = self.headings[i]
        px, py = self.points[i]
        return px - math.sin(h) * lateral, py + math.cos(h) * lateral

    def heading_at(self, i):
        return self.headings[i % self.count]

    def curvature(self, i, span=4):
        """Signed heading change over the next `span` waypoints (radians)."""
        a = self.headings[i % self.count]
        b = self.headings[(i + span) % self.count]
        d = b - a
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        return d

    def nearest(self, x, y, hint, window=5):
        """(index, t, signed lateral distance) of the closest segment near hint.

        Lateral distance is positive to the right of the direction of travel.
        """
        n = self.count
        pts = self.points
        best_i, best_t, best_d2 = hint % n, 0.0, 1e18
        for k in range(-window, window + 1):
            i = (hint + k) % n
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            dx = bx - ax
            dy = by - ay
            ll = dx * dx + dy * dy
            t = ((x - ax) * dx + (y - ay) * dy) / ll
            t = 0.0 if t < 0 else (1.0 if t > 1 else t)
            ex = x - (ax + dx * t)
            ey = y - (ay + dy * t)
            d2 = ex * ex + ey * ey
            if d2 < best_d2:
                best_i, best_t, best_d2 = i, t, d2
        ax, ay = pts[best_i]
        bx, by = pts[(best_i + 1) % n]
        # sign from the cross product of the segment and the offset
        cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        d = math.sqrt(best_d2)
        return best_i, best_t, (d if cross >= 0 else -d)

    def nearest_global(self, x, y):
        best_i, best_d = 0, 1e18
        for i, (px, py) in enumerate(self.points):
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    def surface(self, lateral):
        a = abs(lateral)
        if a <= self.road:
            return ROAD
        if a <= self.road + self.curb:
            return CURB
        return DROP if self.drop else OFF

    def on_patch(self, x, y):
        for px, py, r in self.patches:
            if (x - px) ** 2 + (y - py) ** 2 < r * r:
                return True
        return False

    def on_pad(self, x, y):
        for px, py, _h in self.pads:
            if abs(x - px) < 6 and abs(y - py) < 6:
                return True
        return False

    def grid_slot(self, slot):
        """Start position for grid slot 0 (pole) and up: two abreast, behind the line."""
        i = (-2 - (slot // 2) * 3) % self.count
        side = -self.road * 0.45 if slot % 2 == 0 else self.road * 0.45
        x, y = self.place(i, side)
        return x, y, self.headings[i], i

    def min_clearance(self, skip=None):
        """Smallest distance between two parts of the centre line that are far
        apart along the lap. Below 2 * (road + curb) the roads would overlap."""
        n = self.count
        skip = skip or int((self.road + self.curb) * 4 / STEP) + 2
        best = 1e9
        pts = self.points
        for i in range(n):
            xi, yi = pts[i]
            for j in range(i + skip, i + n - skip + 1):
                xj, yj = pts[j % n]
                d = (xi - xj) ** 2 + (yi - yj) ** 2
                if d < best:
                    best = d
        return math.sqrt(best)
