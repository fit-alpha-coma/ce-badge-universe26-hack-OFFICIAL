# Track geometry and texture.
#
# A track is a closed loop of control points in texel space. It is smoothed
# into waypoints, painted into one square texture at startup (no image asset
# needed) and queried for "how far along" and "how far off the road" a kart is.

import math

SIZE = 256          # texture is SIZE x SIZE texels; one texel = one world unit
ROAD = 15           # half-width of the tarmac
CURB = 3            # curb stripe outside the tarmac
STEP = 6            # spacing between smoothed waypoints

# Clockwise in screen space (y grows downwards). The first point is the start.
LAYOUT = (
    (36, 176), (36, 120), (46, 66), (84, 32), (136, 38), (154, 80),
    (126, 112), (134, 150), (178, 152), (188, 100), (198, 46), (222, 34),
    (234, 96), (230, 176), (210, 220), (160, 228), (110, 214), (66, 228),
    (40, 214),
)


def _catmull(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    return (
        0.5 * (2 * p1[0] + (p2[0] - p0[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
               + (3 * p1[0] - p0[0] - 3 * p2[0] + p3[0]) * t3),
        0.5 * (2 * p1[1] + (p2[1] - p0[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
               + (3 * p1[1] - p0[1] - 3 * p2[1] + p3[1]) * t3),
    )


class Track:
    def __init__(self, layout=LAYOUT):
        self.points = self._smooth(layout)
        self.count = len(self.points)
        self.texture = None

    def _smooth(self, layout):
        n = len(layout)
        dense = []
        for i in range(n):
            p0, p1, p2, p3 = layout[i - 1], layout[i], layout[(i + 1) % n], layout[(i + 2) % n]
            for k in range(16):
                dense.append(_catmull(p0, p1, p2, p3, k / 16))
        # resample to an even spacing so waypoint index tracks distance
        out = [dense[0]]
        carry = 0.0
        for i in range(1, len(dense) + 1):
            a, b = dense[i - 1], dense[i % len(dense)]
            seg = math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
            d = STEP - carry
            while d <= seg:
                t = d / seg
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                d += STEP
            carry = seg - (d - STEP)
        if math.sqrt((out[-1][0] - out[0][0]) ** 2 + (out[-1][1] - out[0][1]) ** 2) < STEP / 2:
            out.pop()
        return out

    def heading_at(self, i):
        a = self.points[i % self.count]
        b = self.points[(i + 1) % self.count]
        return math.atan2(b[1] - a[1], b[0] - a[0])

    def nearest(self, x, y, hint):
        """Return (index, t, distance) of the closest segment near `hint`."""
        best = (hint, 0.0, 1e9)
        n = self.count
        pts = self.points
        for k in range(-4, 6):
            i = (hint + k) % n
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            dx, dy = bx - ax, by - ay
            ll = dx * dx + dy * dy
            t = ((x - ax) * dx + (y - ay) * dy) / ll
            t = 0.0 if t < 0 else (1.0 if t > 1 else t)
            ex, ey = ax + dx * t - x, ay + dy * t - y
            d = ex * ex + ey * ey
            if d < best[2]:
                best = (i, t, d)
        return best[0], best[1], math.sqrt(best[2])

    def nearest_global(self, x, y):
        best_i, best_d = 0, 1e18
        for i, (px, py) in enumerate(self.points):
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best_d:
                best_i, best_d = i, d
        return best_i

    def paint(self):
        """Draw the track into a SIZE x SIZE texture. Call once at startup."""
        tex = image(SIZE, SIZE)
        grass_a = color.rgb(64, 156, 64)
        grass_b = color.rgb(52, 136, 52)
        tex.pen = grass_a
        tex.clear()
        tex.pen = grass_b
        for gy in range(0, SIZE, 16):
            for gx in range((gy // 16) % 2 * 16, SIZE, 32):
                tex.rectangle(gx, gy, 16, 16)

        pts = self.points
        n = self.count
        # curbs: alternating red and white blocks under the tarmac
        red = color.rgb(214, 40, 40)
        white = color.rgb(240, 240, 240)
        for i in range(n):
            tex.pen = red if (i // 2) % 2 else white
            self._stroke(tex, pts[i], pts[(i + 1) % n], ROAD + CURB)
        tex.pen = color.rgb(96, 98, 108)
        for i in range(n):
            self._stroke(tex, pts[i], pts[(i + 1) % n], ROAD)
        self._start_line(tex)
        self.texture = tex
        return tex

    def _stroke(self, tex, a, b, r):
        steps = max(1, int(math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) / 2))
        for s in range(steps):
            t = s / steps
            tex.circle(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, r)

    def _start_line(self, tex):
        h = self.heading_at(0)
        x0, y0 = self.points[0]
        rx, ry = -math.sin(h), math.cos(h)
        fx, fy = math.cos(h), math.sin(h)
        for row in range(2):
            for k in range(-ROAD, ROAD, 3):
                tex.pen = color.rgb(20, 20, 20) if (k // 3 + row) % 2 else color.rgb(250, 250, 250)
                cx = x0 + rx * k + fx * row * 3
                cy = y0 + ry * k + fy * row * 3
                tex.rectangle(int(cx), int(cy), 3, 3)
