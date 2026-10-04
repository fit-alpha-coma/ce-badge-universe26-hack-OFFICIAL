# Mode 7 world renderer for the 320x240 HIRES screen.
#
# The sky and floor are drawn into a 160x120 image: each floor row is one
# blit_hspan() along a line across the track texture, rotated by the camera
# heading. That image is scaled up 2x in one blit, then karts, item boxes and
# scenery are drawn on top at full resolution.

import math
from geom import SIZE
from scenery import SCENERY

LW = 160            # floor image size (pixels)
LH = 120
HORIZON = 34
FOV = 64
CAM_HEIGHT = 18.0
CAM_BACK = 38.0
FAR = 340.0
FOCAL = (LW / 2) / math.tan(math.radians(FOV / 2))
# world units across a 32 px kart cell, chosen so the player (CAM_BACK ahead of
# the camera) is drawn at exactly 2x: 32 * 2 = SPRITE_WORLD * 2 * FOCAL / CAM_BACK
SPRITE_WORLD = 32.0 * CAM_BACK / FOCAL
NEAR = 20.0


def _mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


class World:
    def __init__(self, art, track_index, spec):
        self.art = art
        self.spec = spec
        self.tex, self.mini = art.track(track_index)
        self.scenery_spots = SCENERY.get(spec["key"], ())
        self.inv = 1.0 / SIZE
        self.view = image(LW, LH)
        self.x = self.y = 0.0
        self.angle = 0.0
        self.shake = 0.0
        self.rows = []
        self.fog = []
        haze = spec["haze"]
        for y in range(HORIZON + 1, LH):
            z = CAM_HEIGHT * FOCAL / (y - HORIZON + 0.5)
            if z > FAR * 1.7:
                continue
            self.rows.append((y, z, z * (LW / 2) / FOCAL))
            fade = (z - FAR * 0.42) / (FAR * 1.2)
            fade = 0.0 if fade < 0 else (1.0 if fade > 1 else fade)
            self.fog.append(color.rgb(haze[0], haze[1], haze[2], int(fade * 235)) if fade > 0 else None)
        self.top = self.rows[0][0]
        self.sky = self._paint_sky()

    # -- camera ------------------------------------------------------------------

    def follow(self, x, y, angle, dt, snap=False):
        """Trail the kart; the heading eases in so drifts swing the view."""
        if snap:
            self.angle = angle
        else:
            d = angle - self.angle
            while d > math.pi:
                d -= 2 * math.pi
            while d < -math.pi:
                d += 2 * math.pi
            self.angle += d * min(1.0, dt * 7.0)
        self.x = x - math.cos(self.angle) * CAM_BACK
        self.y = y - math.sin(self.angle) * CAM_BACK

    def project(self, x, y):
        """World point to (sx, sy, scale, z) in HIRES pixels, or None if behind."""
        dx = x - self.x
        dy = y - self.y
        ca = math.cos(self.angle)
        sa = math.sin(self.angle)
        z = dx * ca + dy * sa
        if z < NEAR or z > FAR * 1.6:
            return None
        s = FOCAL / z
        lat = -dx * sa + dy * ca
        return (LW / 2 + lat * s) * 2, (HORIZON + CAM_HEIGHT * s) * 2, s * 2, z

    # -- sky and floor -----------------------------------------------------------

    def _paint_sky(self):
        spec = self.spec
        top_c, low_c = spec["sky"]
        h = self.top
        sky = image(LW * 2, h)
        for y in range(h):
            sky.pen = color.rgb(*_mix(top_c, low_c, y / max(1, h - 1)))
            sky.rectangle(0, y, LW * 2, 1)
        key = spec["key"]
        hill = spec["hills"]
        if key == "frost":
            sky.pen = color.rgb(255, 255, 255)
            for i in range(40):
                sky.put((i * 73) % (LW * 2), (i * 37) % (h - 8))
            sky.pen = color.rgb(90, 230, 170, 90)
            for x in range(0, LW * 2, 2):
                yy = 6 + int(math.sin(x / 23.0) * 3 + math.sin(x / 9.0) * 1.5)
                sky.rectangle(x, yy, 2, 5)
        if key == "meadow":
            sky.pen = color.rgb(255, 255, 255, 220)
            for cx, cy in ((30, 8), (120, 5), (210, 10), (280, 6)):
                sky.circle(cx, cy, 4)
                sky.circle(cx + 5, cy - 1, 5)
                sky.circle(cx + 10, cy, 4)
        base = h
        for i, (cx, hw, hh) in enumerate(((30, 34, 16), (95, 26, 11), (150, 40, 20),
                                          (215, 30, 13), (275, 36, 18))):
            for ox in (0, -LW * 2, LW * 2):
                sky.pen = color.rgb(*hill)
                if key == "canyon":   # flat-topped mesas
                    sky.rectangle(cx - hw // 2 + ox, base - hh, hw, hh)
                    sky.triangle(cx - hw // 2 - 6 + ox, base, cx - hw // 2 + ox, base - hh, cx - hw // 2 + ox, base)
                else:
                    sky.triangle(cx - hw + ox, base, cx + ox, base - hh, cx + hw + ox, base)
                if spec.get("snow"):
                    sky.pen = color.rgb(240, 244, 252)
                    sky.triangle(cx - hw // 4 + ox, base - hh * 3 // 4, cx + ox, base - hh,
                                 cx + hw // 4 + ox, base - hh * 3 // 4)
        if key == "volcano":
            sky.pen = color.rgb(70, 30, 30)
            sky.triangle(120, base, 160, base - 24, 200, base)
            sky.pen = color.rgb(255, 120, 30)
            sky.triangle(152, base - 20, 160, base - 24, 168, base - 20)
            sky.pen = color.rgb(90, 80, 80, 160)
            for k in range(5):
                sky.circle(160 + k * 3, base - 28 - k * 5, 3 + k)
        haze = spec["haze"]
        sky.pen = color.rgb(haze[0], haze[1], haze[2])
        sky.rectangle(0, base - 2, LW * 2, 2)
        return sky

    def draw_background(self):
        v = self.view
        off = int(-math.degrees(self.angle) * LW / FOV) % (LW * 2)
        v.blit(self.sky, vec2(-off, 0))
        if off > LW:
            v.blit(self.sky, vec2(LW * 2 - off, 0))
        ca = math.cos(self.angle)
        sa = math.sin(self.angle)
        inv = self.inv
        cx, cy = self.x, self.y
        tex = self.tex
        blit = v.blit_hspan
        for y, z, hw in self.rows:
            mx = cx + ca * z
            my = cy + sa * z
            ox = -sa * hw
            oy = ca * hw
            blit(tex, 0, y, LW, (mx - ox) * inv, (my - oy) * inv, (mx + ox) * inv, (my + oy) * inv)
        i = 0
        for y, z, hw in self.rows:
            pen = self.fog[i]
            i += 1
            if pen is None:
                break
            v.pen = pen
            v.rectangle(0, y, LW, 1)
        sy = 0
        if self.shake > 0:
            sy = 2 if int(self.shake * 40) % 2 else -2
        screen.blit(v, rect(0, sy, LW * 2, LH * 2))

    # -- sprites -----------------------------------------------------------------

    def kart_sprite(self, kart, scale):
        """Pick the view of `kart` the camera sees, and whether to mirror it."""
        bearing = math.atan2(kart.y - self.y, kart.x - self.x)
        view = kart.heading - bearing
        while view > math.pi:
            view -= 2 * math.pi
        while view < -math.pi:
            view += 2 * math.pi
        a = abs(view)
        if a < 0.35:
            v = 0
        elif a < 1.15:
            v = 1
        elif a < 2.4:
            v = 2
        else:
            v = 3
        sheet = self.art.karts[kart.char] if scale >= 1.0 else self.art.karts_half[kart.char]
        return sheet[v], (v in (1, 2) and view < 0)

    def draw_sprites(self, karts, items, now, ghost=None, highlight=None):
        art = self.art
        draw = []
        ca = math.cos(self.angle)
        sa = math.sin(self.angle)
        camx, camy = self.x, self.y
        far = FAR * 1.4
        for sx, sy, kind in self.scenery_spots:
            dx = sx - camx
            dy = sy - camy
            z = dx * ca + dy * sa
            if z < NEAR or z > far:
                continue
            lat = -dx * sa + dy * ca
            if abs(lat) > z * 0.75:
                continue
            draw.append((z, 0, kind, sx, sy))
        if items is not None:
            for b in items.boxes:
                if b.active:
                    draw.append((self._z(b.x, b.y), 1, 0, b.x, b.y))
            for bug in items.bugs:
                draw.append((self._z(bug.x, bug.y), 2, 0, bug.x, bug.y))
            for duck in items.ducks:
                draw.append((self._z(duck.x, duck.y), 3, 0, duck.x, duck.y))
        for k in karts:
            if k.fall > 0:
                continue
            draw.append((self._z(k.x, k.y), 4, k, k.x, k.y))
        if ghost is not None:
            draw.append((self._z(ghost[0], ghost[1]), 5, ghost, ghost[0], ghost[1]))
        draw.sort(key=lambda d: -d[0])
        box_frame = (now // 120) % 4
        for z, kind, obj, wx, wy in draw:
            p = self.project(wx, wy)
            if p is None:
                continue
            px, py, s, _z = p
            if kind == 0:
                img = art.scenery[obj]
                w = 6.0 * s
                h = w * 32 / 24
                self._blit(img, px - w / 2, py - h, w, h)
            elif kind == 1:
                w = 4.5 * s
                self._blit(art.box[box_frame], px - w / 2, py - w * 1.35, w, w)
            elif kind == 2:
                w = 4.0 * s
                self._blit(art.bug, px - w / 2, py - w * 0.75, w, w * 0.75)
            elif kind == 3:
                w = 4.0 * s
                hop = abs(math.sin(now / 90.0)) * w * 0.3
                self._blit(art.duck, px - w / 2, py - w * 0.9 - hop, w, w * 0.88)
            elif kind == 4:
                self._draw_kart(obj, px, py, s, now, obj is highlight)
            else:
                self._draw_ghost(obj, px, py, s)

    def _z(self, x, y):
        return (x - self.x) * math.cos(self.angle) + (y - self.y) * math.sin(self.angle)

    def _blit(self, img, x, y, w, h, flip=False):
        if w < 1.5 or x > 320 or x + w < 0:
            return
        f = image.NEAREST if w >= img.width * 1.9 else image.BILINEAR
        if flip:
            screen.blit(img, rect(x + w, y, -w, h), f)
        else:
            screen.blit(img, rect(x, y, w, h), f)

    def _draw_kart(self, k, px, py, s, now, is_player):
        w = SPRITE_WORLD * s
        scale = w / 32.0
        img, flip = self.kart_sprite(k, scale)
        if is_player:
            # snap the player's own kart to an exact 2x for crisp pixels
            w = 64.0
            px = round(px)
            py = round(py)
        h = w
        lift = 0.0
        if k.hop > 0:
            lift = math.sin(k.hop / 0.18 * math.pi) * w * 0.12
        elif k.spin > 0:
            lift = 0.0
        elif abs(k.forward_speed()) > 8:
            lift = (1.0 if (now // (50 if k.surface >= 2 else 110)) % 2 else 0.0) * max(1.0, w / 40)
        # shadow
        screen.pen = color.rgb(0, 0, 0, 90)
        screen.shape(shape.rounded_rectangle(px - w * 0.36, py - h * 0.08, w * 0.72, h * 0.13, h * 0.06))
        top = py - h * 0.97 - lift
        self._blit(img, px - w / 2, top, w, h, flip)
        if k.shield > 0:
            a = 70 + int(40 * math.sin(now / 80.0))
            screen.pen = color.rgb(110, 200, 255, a)
            screen.shape(shape.circle(px, top + h * 0.55, w * 0.58))
        if k.drift and k.level:
            col = ((90, 170, 255), (255, 160, 40), (255, 90, 220))[k.level - 1]
            screen.pen = color.rgb(col[0], col[1], col[2])
            for side in (-1, 1):
                r = max(1.5, w * 0.05) * (1.4 if (now // 60) % 2 else 1.0)
                screen.shape(shape.circle(px + side * w * 0.32, py - h * 0.06, r))
        if k.boost > 0:
            for side in (-1, 1):
                fl = w * (0.12 + 0.05 * ((now // 40) % 3))
                screen.pen = color.rgb(255, 200, 60, 230)
                screen.shape(shape.circle(px + side * w * 0.14, py - h * 0.07, fl * 0.5))
                screen.pen = color.rgb(255, 110, 30, 200)
                screen.shape(shape.circle(px + side * w * 0.14, py - h * 0.03, fl * 0.35))
        if k.surface >= 2 and abs(k.forward_speed()) > 15 and k.fall <= 0:
            screen.pen = color.rgb(*(self.spec["ground"][1] + (200,)))
            for side in (-1, 1):
                screen.shape(shape.circle(px + side * w * 0.3 - side * ((now // 70) % 3), py - h * 0.04,
                                          max(1.5, w * 0.05)))

    def _draw_ghost(self, g, px, py, s):
        w = SPRITE_WORLD * s
        img = self.art.karts[g[3]][0] if w >= 32 else self.art.karts_half[g[3]][0]
        img.alpha = 110
        self._blit(img, px - w / 2, py - w * 0.97, w, w)
        img.alpha = 255
