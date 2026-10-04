# Mode 7 renderer: a flat textured floor seen in perspective, plus a sky band
# and scaled sprites.
#
# Each screen row below the horizon shows one straight line across the track
# texture. Its distance from the camera depends only on the row, so it is
# precomputed. Per frame we only rotate that line by the camera heading and copy
# it with screen.blit_hspan(), which samples the texture in C.

import math

W = 160
H = 120
HORIZON = 34        # screen row of the horizon
FOV = 64            # horizontal field of view in degrees
CAM_HEIGHT = 15     # camera height in texels
CAM_BACK = 30       # camera distance behind the kart it follows
FAR = 330           # rows further than this fade into the haze
FOCAL = (W / 2) / math.tan(math.radians(FOV / 2))

SKY_TOP = (70, 120, 220)
SKY_LOW = (170, 205, 245)
HAZE = (150, 190, 170)


class Camera:
    def __init__(self, texture, size):
        self.tex = texture
        self.inv = 1.0 / size
        self.x = 0.0
        self.y = 0.0
        self.angle = 0.0
        # per-row distance and half-width of the visible floor line
        self.rows = []
        self.fog = []
        for y in range(HORIZON + 1, H):
            z = CAM_HEIGHT * FOCAL / (y - HORIZON + 0.5)
            if z > FAR * 1.6:
                continue
            self.rows.append((y, z, z * (W / 2) / FOCAL))
            fade = (z - FAR * 0.45) / (FAR * 1.15)
            fade = 0 if fade < 0 else (1 if fade > 1 else fade)
            self.fog.append(color.rgb(HAZE[0], HAZE[1], HAZE[2], int(fade * 230)) if fade > 0 else None)
        self.top = self.rows[0][0]
        self.sky = self._paint_sky()

    def follow(self, x, y, angle):
        self.angle = angle
        self.x = x - math.cos(angle) * CAM_BACK
        self.y = y - math.sin(angle) * CAM_BACK

    def _paint_sky(self):
        # two screens wide so it can scroll with the heading and wrap
        sky = image(W * 2, self.top)
        for y in range(self.top):
            t = y / max(1, self.top - 1)
            sky.pen = color.rgb(
                int(SKY_TOP[0] + (SKY_LOW[0] - SKY_TOP[0]) * t),
                int(SKY_TOP[1] + (SKY_LOW[1] - SKY_TOP[1]) * t),
                int(SKY_TOP[2] + (SKY_LOW[2] - SKY_TOP[2]) * t),
            )
            sky.rectangle(0, y, W * 2, 1)
        # distant snowy hills, periodic over the sky width
        base = self.top
        for i, (cx, hw, hh) in enumerate(((30, 34, 18), (95, 26, 13), (150, 40, 22),
                                         (215, 30, 15), (275, 36, 20))):
            for ox in (0, -W * 2, W * 2):
                sky.pen = color.rgb(96, 112, 150)
                sky.triangle(cx - hw + ox, base, cx + ox, base - hh, cx + hw + ox, base)
                sky.pen = color.rgb(235, 240, 250)
                sky.triangle(cx - hw // 4 + ox, base - hh * 3 // 4, cx + ox, base - hh,
                             cx + hw // 4 + ox, base - hh * 3 // 4)
        sky.pen = color.rgb(HAZE[0], HAZE[1], HAZE[2])
        sky.rectangle(0, base - 2, W * 2, 2)
        return sky

    def draw_sky(self):
        # one full turn scrolls the sky by 360 / FOV screens; wrap at 2 screens
        off = int(-math.degrees(self.angle) * W / FOV) % (W * 2)
        screen.blit(self.sky, vec2(-off, 0))
        if off > W:
            screen.blit(self.sky, vec2(W * 2 - off, 0))

    def draw_floor(self):
        fx = math.cos(self.angle)
        fy = math.sin(self.angle)
        rx, ry = -fy, fx
        inv = self.inv
        cx, cy = self.x, self.y
        tex = self.tex
        blit = screen.blit_hspan
        for y, z, hw in self.rows:
            mx = cx + fx * z
            my = cy + fy * z
            blit(tex, 0, y, W,
                 (mx - rx * hw) * inv, (my - ry * hw) * inv,
                 (mx + rx * hw) * inv, (my + ry * hw) * inv)
        i = 0
        for y, z, hw in self.rows:
            pen = self.fog[i]
            i += 1
            if pen is None:
                break
            screen.pen = pen
            screen.rectangle(0, y, W, 1)

    def draw(self):
        self.draw_sky()
        self.draw_floor()

    def project(self, x, y):
        """World point to (screen_x, screen_y, scale) or None if behind."""
        dx = x - self.x
        dy = y - self.y
        fx = math.cos(self.angle)
        fy = math.sin(self.angle)
        z = dx * fx + dy * fy
        if z < 14:  # behind the player and too close to draw
            return None
        lat = -dx * fy + dy * fx
        s = FOCAL / z
        return W / 2 + lat * s, HORIZON + CAM_HEIGHT * s, s, z
