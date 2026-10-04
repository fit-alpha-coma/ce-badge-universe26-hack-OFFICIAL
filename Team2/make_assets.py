#!/usr/bin/env python3
"""Generate Super Mona Kart's art into Team2/super_mona_kart/assets.

Run from the repository root after changing a track or a sprite:

    python3 Team2/make_assets.py

Needs Pillow (desktop only; the badge just loads the PNGs). Sprites are drawn
as pixel art at 1x and shown at exact 2x on the badge's 320x240 HIRES screen,
so they stay crisp. Distant karts are scaled down from a half-size copy with
bilinear filtering, which keeps them smooth instead of shimmering.

Character side and front views reuse the badge apps' own art (Flappy, Plucky
Cluck, Snarky Sciuridae, Bee Amazed); back views are drawn here to match.
"""

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
APP = HERE / "super_mona_kart"
OUT = APP / "assets"
sys.path.insert(0, str(APP))

import config  # noqa: E402
from geom import Geometry, SIZE  # noqa: E402

CELL = 32           # kart sprite cell (1x)
VIEWS = 4           # back, three-quarter, side, front
CLEAR = (0, 0, 0, 0)
INK = (20, 18, 30, 255)


def frames(path, fw, fh):
    im = Image.open(REPO / path).convert("RGBA")
    cols = im.width // fw
    rows = im.height // fh
    return [im.crop((c * fw, r * fh, c * fw + fw, r * fh + fh)) for r in range(rows) for c in range(cols)]


def rgba(c, a=255):
    return (c[0], c[1], c[2], a)


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3]) + (255,)


def outline(img, color=INK):
    """Add a 1px outline around opaque pixels (pixel-art readability)."""
    src = img.copy()
    px = src.load()
    out = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and px[nx, ny][3] > 128:
                    out[x, y] = color
                    break
    return img


def crop_alpha(img):
    box = img.getbbox()
    return img.crop(box) if box else img


# --- karts -------------------------------------------------------------------

def kart_back(d, body):
    hi, lo = shade(body, 1.25), shade(body, 0.6)
    d.rectangle((2, 21, 7, 30), fill=(34, 34, 40, 255))        # tyres
    d.rectangle((24, 21, 29, 30), fill=(34, 34, 40, 255))
    d.rectangle((3, 22, 6, 23), fill=(70, 70, 80, 255))
    d.rectangle((25, 22, 28, 23), fill=(70, 70, 80, 255))
    d.rounded_rectangle((6, 19, 25, 28), 3, fill=rgba(body))
    d.rectangle((7, 19, 24, 20), fill=hi)
    d.rectangle((7, 26, 24, 28), fill=lo)
    d.rectangle((12, 24, 19, 26), fill=(236, 236, 228, 255))     # plate
    d.ellipse((9, 27, 12, 30), fill=(120, 120, 128, 255))        # exhausts
    d.ellipse((19, 27, 22, 30), fill=(120, 120, 128, 255))


def kart_three_quarter(d, body):
    hi, lo = shade(body, 1.25), shade(body, 0.6)
    d.rectangle((1, 21, 6, 30), fill=(34, 34, 40, 255))
    d.ellipse((22, 23, 30, 31), fill=(34, 34, 40, 255))
    d.ellipse((24, 25, 28, 29), fill=(110, 110, 120, 255))
    d.polygon(((5, 19), (24, 19), (31, 23), (31, 27), (24, 28), (5, 28)), fill=rgba(body))
    d.rectangle((6, 19, 23, 20), fill=hi)
    d.rectangle((6, 26, 23, 28), fill=lo)
    d.rectangle((10, 24, 17, 26), fill=(236, 236, 228, 255))
    d.ellipse((7, 27, 10, 30), fill=(120, 120, 128, 255))


def kart_side(d, body):
    hi, lo = shade(body, 1.25), shade(body, 0.6)
    d.polygon(((2, 21), (24, 21), (31, 24), (31, 27), (2, 27)), fill=rgba(body))
    d.rectangle((3, 21, 23, 22), fill=hi)
    d.rectangle((3, 26, 30, 27), fill=lo)
    for cx in (7, 24):
        d.ellipse((cx - 4, 24, cx + 4, 31), fill=(34, 34, 40, 255))
        d.ellipse((cx - 2, 26, cx + 2, 29), fill=(120, 120, 128, 255))


def kart_front(d, body):
    hi, lo = shade(body, 1.25), shade(body, 0.6)
    d.rectangle((2, 22, 7, 30), fill=(34, 34, 40, 255))
    d.rectangle((24, 22, 29, 30), fill=(34, 34, 40, 255))
    d.rounded_rectangle((6, 20, 25, 28), 3, fill=rgba(body))
    d.rectangle((7, 20, 24, 21), fill=hi)
    d.rectangle((7, 27, 24, 28), fill=lo)
    d.ellipse((8, 23, 11, 26), fill=(255, 246, 180, 255))        # headlights
    d.ellipse((20, 23, 23, 26), fill=(255, 246, 180, 255))
    d.rectangle((13, 24, 18, 25), fill=(40, 40, 48, 255))        # grille


def rider_back(key, ch):
    """Back-of-character art, 32x32, rider sits from row 3 to row 21."""
    img = Image.new("RGBA", (CELL, CELL), CLEAR)
    d = ImageDraw.Draw(img)
    if key == "mona":
        p, p2, p3 = (110, 52, 196, 255), (82, 34, 150, 255), (150, 96, 228, 255)
        # tentacles curling out either side of the seat
        for cx in (8, 23):
            d.arc((cx - 4, 13, cx + 3, 21), 200, 340 if cx < 16 else 520, fill=p2, width=2)
        d.ellipse((11, 13, 20, 22), fill=p2)          # body
        d.ellipse((9, 3, 22, 15), fill=p)             # round cat head
        d.polygon(((9, 8), (10, 0), (14, 4)), fill=p)  # ears
        d.polygon(((22, 8), (21, 0), (17, 4)), fill=p)
        d.ellipse((12, 5, 18, 8), fill=p3)            # highlight
        img = outline(img, (255, 255, 255, 255))
        img = outline(img, INK)
    elif key == "cluck":
        w, w2 = (236, 232, 222, 255), (196, 190, 180, 255)
        d.ellipse((8, 7, 23, 22), fill=w)
        d.ellipse((10, 15, 21, 22), fill=w2)
        d.ellipse((13, 2, 19, 8), fill=w)
        d.polygon(((13, 3), (15, 0), (16, 3), (18, 0), (19, 4)), fill=(150, 30, 34, 255))
        d.polygon(((14, 16), (17, 16), (16, 21)), fill=(240, 240, 236, 255))   # tail tuft
        img = outline(img)
    elif key == "sciuri":
        b, b2, t = (150, 90, 48, 255), (118, 66, 34, 255), (100, 56, 30, 255)
        d.ellipse((15, 0, 31, 20), fill=t)           # big tail behind, curling up
        d.ellipse((19, 3, 28, 14), fill=(132, 78, 42, 255))
        d.ellipse((8, 5, 20, 16), fill=b)            # head
        d.polygon(((9, 8), (9, 2), (12, 6)), fill=b2)
        d.polygon(((19, 8), (19, 2), (16, 6)), fill=b2)
        d.ellipse((8, 12, 21, 22), fill=b)
        img = outline(img)
    elif key == "buzz":
        y, k = (246, 196, 34, 255), (40, 30, 24, 255)
        d.ellipse((2, 4, 13, 13), fill=(236, 246, 255, 200))     # wings
        d.ellipse((18, 4, 29, 13), fill=(236, 246, 255, 200))
        d.ellipse((8, 6, 23, 21), fill=y)
        for row in (10, 15):
            d.rectangle((9, row, 22, row + 2), fill=k)
        d.line(((13, 6), (11, 1)), fill=k)
        d.line(((18, 6), (20, 1)), fill=k)
        img = outline(img)
    else:
        img = Image.new("RGBA", (CELL, CELL), CLEAR)
        img.alpha_composite(eco("back", key), (4, 0))
    return img


# --- open-source mascots, drawn here as original pixel art --------------------
# Tux (Linux, Larry Ewing), Ferris (Rust, CC0), the Go gopher (Renee French,
# CC BY 4.0), Duke (Java, BSD) and the Android robot (Google, CC BY 3.0).
# 24x24, rider sits with its lower rows hidden by the kart.

BLACKISH = (22, 22, 28, 255)
WHITE = (246, 246, 240, 255)


def eco(view, key):
    img = Image.new("RGBA", (24, 24), CLEAR)
    d = ImageDraw.Draw(img)
    if key == "tux":
        beak = (250, 186, 32, 255)
        if view == "front":
            d.ellipse((5, 8, 18, 24), fill=BLACKISH)
            d.ellipse((8, 11, 15, 24), fill=WHITE)
            d.ellipse((6, 0, 17, 12), fill=BLACKISH)
            d.ellipse((8, 3, 15, 10), fill=WHITE)
            d.point((10, 5), fill=BLACKISH)
            d.point((13, 5), fill=BLACKISH)
            d.polygon(((9, 7), (14, 7), (11, 10)), fill=beak)
            d.polygon(((3, 12), (6, 10), (6, 18)), fill=BLACKISH)
            d.polygon(((20, 12), (17, 10), (17, 18)), fill=BLACKISH)
        elif view == "side":
            d.ellipse((5, 8, 18, 24), fill=BLACKISH)
            d.ellipse((11, 11, 17, 24), fill=WHITE)
            d.ellipse((6, 0, 17, 12), fill=BLACKISH)
            d.ellipse((12, 3, 16, 9), fill=WHITE)
            d.point((14, 5), fill=BLACKISH)
            d.polygon(((16, 6), (21, 7), (16, 9)), fill=beak)
            d.polygon(((7, 12), (10, 11), (5, 19)), fill=(50, 50, 58, 255))
        else:
            d.ellipse((5, 8, 18, 24), fill=BLACKISH)
            d.ellipse((6, 0, 17, 12), fill=BLACKISH)
            d.polygon(((3, 12), (6, 10), (6, 18)), fill=BLACKISH)
            d.polygon(((20, 12), (17, 10), (17, 18)), fill=BLACKISH)
            d.ellipse((8, 2, 12, 5), fill=(70, 70, 82, 255))
    elif key == "ferris":
        o, o2 = (247, 80, 20, 255), (196, 52, 10, 255)
        if view == "front":
            for x in (4, 8, 15, 19):
                d.line(((x, 18), (x - 1 if x < 12 else x + 1, 22)), fill=o2, width=1)
            d.ellipse((2, 10, 21, 21), fill=o)
            d.line(((8, 10), (8, 5)), fill=o2)
            d.line(((15, 10), (15, 5)), fill=o2)
            d.ellipse((6, 2, 10, 6), fill=WHITE)
            d.ellipse((13, 2, 17, 6), fill=WHITE)
            d.point((8, 4), fill=BLACKISH)
            d.point((15, 4), fill=BLACKISH)
            d.arc((8, 13, 15, 18), 20, 160, fill=BLACKISH)
            d.pieslice((0, 4, 6, 11), 200, 520, fill=o)      # claws up
            d.pieslice((17, 4, 23, 11), 20, 340, fill=o)
        elif view == "side":
            d.ellipse((2, 11, 18, 21), fill=o)
            d.line(((13, 11), (14, 5)), fill=o2)
            d.ellipse((12, 2, 16, 6), fill=WHITE)
            d.point((15, 4), fill=BLACKISH)
            d.pieslice((15, 8, 23, 15), 300, 610, fill=o)      # claw forward
            for x in (5, 9, 13):
                d.line(((x, 20), (x - 2, 23)), fill=o2)
        else:
            d.ellipse((2, 9, 21, 21), fill=o)
            for x in range(4, 21, 4):                           # sprocket bumps
                d.rectangle((x, 8, x + 1, 9), fill=o2)
            d.pieslice((0, 4, 6, 11), 200, 520, fill=o)
            d.pieslice((17, 4, 23, 11), 20, 340, fill=o)
            d.ellipse((8, 12, 15, 17), fill=(255, 130, 70, 255))
    elif key == "gopher":
        b, b2, tan = (106, 215, 229, 255), (70, 170, 190, 255), (240, 214, 170, 255)
        if view == "front":
            d.ellipse((5, 4, 18, 24), fill=b)
            d.ellipse((5, 2, 8, 5), fill=b2)
            d.ellipse((15, 2, 18, 5), fill=b2)
            d.ellipse((6, 5, 11, 10), fill=WHITE)
            d.ellipse((12, 5, 17, 10), fill=WHITE)
            d.point((9, 8), fill=BLACKISH)
            d.point((14, 8), fill=BLACKISH)
            d.ellipse((9, 10, 14, 13), fill=tan)
            d.point((11, 10), fill=BLACKISH)
            d.rectangle((11, 13, 12, 14), fill=WHITE)
            d.ellipse((2, 13, 6, 17), fill=tan)
            d.ellipse((17, 13, 21, 17), fill=tan)
        elif view == "side":
            d.ellipse((5, 4, 18, 24), fill=b)
            d.ellipse((7, 2, 10, 5), fill=b2)
            d.ellipse((11, 5, 16, 10), fill=WHITE)
            d.point((14, 8), fill=BLACKISH)
            d.ellipse((15, 10, 20, 13), fill=tan)
            d.point((19, 10), fill=BLACKISH)
            d.rectangle((17, 13, 18, 14), fill=WHITE)
            d.ellipse((13, 14, 17, 18), fill=tan)
        else:
            d.ellipse((5, 4, 18, 24), fill=b)
            d.ellipse((5, 2, 8, 5), fill=b2)
            d.ellipse((15, 2, 18, 5), fill=b2)
            d.ellipse((9, 18, 14, 22), fill=b2)                # little tail
    elif key == "duke":
        red = (226, 28, 40, 255)
        if view == "front":
            d.polygon(((12, 0), (20, 20), (4, 20)), fill=BLACKISH)
            d.ellipse((4, 12, 20, 24), fill=BLACKISH)
            d.polygon(((12, 9), (17, 21), (7, 21)), fill=WHITE)
            d.ellipse((9, 9, 15, 15), fill=red)
            d.ellipse((10, 10, 12, 12), fill=(255, 140, 140, 255))
            d.line(((5, 15), (0, 10)), fill=BLACKISH, width=2)  # a wave
            d.line(((19, 15), (23, 18)), fill=BLACKISH, width=2)
        elif view == "side":
            d.polygon(((10, 0), (18, 20), (4, 20)), fill=BLACKISH)
            d.ellipse((4, 12, 18, 24), fill=BLACKISH)
            d.polygon(((13, 9), (17, 21), (11, 21)), fill=WHITE)
            d.ellipse((15, 9, 21, 15), fill=red)
        else:
            d.polygon(((12, 0), (20, 20), (4, 20)), fill=BLACKISH)
            d.ellipse((4, 12, 20, 24), fill=BLACKISH)
            d.line(((5, 15), (0, 10)), fill=BLACKISH, width=2)
            d.line(((19, 15), (23, 18)), fill=BLACKISH, width=2)
    else:  # android robot
        g = (61, 220, 132, 255)
        if view in ("front", "back"):
            d.line(((8, 4), (6, 1)), fill=g)
            d.line(((15, 4), (17, 1)), fill=g)
            d.pieslice((5, 3, 18, 15), 180, 360, fill=g)
            if view == "front":
                d.point((9, 6), fill=WHITE)
                d.point((14, 6), fill=WHITE)
            d.rounded_rectangle((5, 10, 18, 21), 2, fill=g)
            d.rounded_rectangle((1, 10, 4, 18), 2, fill=g)
            d.rounded_rectangle((19, 10, 22, 18), 2, fill=g)
            d.rectangle((8, 21, 9, 23), fill=g)
            d.rectangle((14, 21, 15, 23), fill=g)
        else:
            d.line(((12, 4), (14, 1)), fill=g)
            d.pieslice((5, 3, 18, 15), 180, 360, fill=g)
            d.point((15, 6), fill=WHITE)
            d.rounded_rectangle((5, 10, 18, 21), 2, fill=g)
            d.rounded_rectangle((10, 10, 13, 18), 2, fill=(40, 180, 100, 255))
            d.rectangle((9, 21, 11, 23), fill=g)
    return outline(img)


def place_rider(canvas, rider, bottom=23):
    r = crop_alpha(rider)
    x = (CELL - r.width) // 2
    y = max(0, bottom - r.height)
    canvas.alpha_composite(r, (x, y))


def kart_sheet(ch, side_rider, front_rider):
    key = ch["key"]
    body = ch["body"]
    sheet = Image.new("RGBA", (CELL * VIEWS, CELL), CLEAR)
    back = rider_back(key, ch)
    for v in range(VIEWS):
        cell = Image.new("RGBA", (CELL, CELL), CLEAR)
        d = ImageDraw.Draw(cell)
        if v == 0:
            cell.alpha_composite(back, (0, 0))
            kart_back(d, body)
        elif v == 1:
            cell.alpha_composite(back, (-2, 0))
            kart_three_quarter(d, body)
        elif v == 2:
            place_rider(cell, side_rider, 25)
            kart_side(d, body)
        else:
            place_rider(cell, front_rider, 25)
            kart_front(d, body)
        cell = outline(cell)
        sheet.alpha_composite(cell, (v * CELL, 0))
    return sheet


# --- small sprites -------------------------------------------------------------

def item_box_sheet():
    greens = [(14, 68, 41), (0, 109, 50), (38, 166, 65), (57, 211, 83)]
    sheet = Image.new("RGBA", (16 * 4, 16), CLEAR)
    for f in range(4):
        img = Image.new("RGBA", (16, 16), CLEAR)
        d = ImageDraw.Draw(img)
        w = [12, 9, 4, 9][f]
        x0 = 8 - w // 2
        d.rectangle((x0, 2, x0 + w - 1, 13), fill=rgba(greens[2]))
        d.rectangle((x0, 2, x0 + w - 1, 3), fill=rgba(greens[3]))
        d.rectangle((x0, 12, x0 + w - 1, 13), fill=rgba(greens[1]))
        if w >= 9:
            d.text((x0 + w // 2 - 2, 3), "?", fill=(255, 255, 255, 255))
        img = outline(img, rgba(greens[0]))
        sheet.alpha_composite(img, (f * 16, 0))
    return sheet


def bug_sprite():
    img = Image.new("RGBA", (16, 12), CLEAR)
    d = ImageDraw.Draw(img)
    for x in (3, 6, 9, 12):
        d.line(((x, 2), (x - 1, 0)), fill=INK)
        d.line(((x, 9), (x - 1, 11)), fill=INK)
    d.ellipse((1, 2, 14, 10), fill=(60, 170, 70, 255))
    d.line(((8, 2), (8, 10)), fill=(20, 80, 30, 255))
    d.ellipse((11, 4, 15, 8), fill=(30, 40, 30, 255))
    d.point((13, 5), fill=(255, 255, 255, 255))
    return outline(img)


def duck_sprite():
    img = Image.new("RGBA", (16, 14), CLEAR)
    d = ImageDraw.Draw(img)
    d.ellipse((1, 6, 13, 13), fill=(255, 214, 40, 255))
    d.ellipse((6, 1, 13, 8), fill=(255, 214, 40, 255))
    d.polygon(((12, 4), (16, 5), (12, 6)), fill=(250, 120, 30, 255))
    d.point((10, 3), fill=INK)
    d.line(((3, 9), (7, 9)), fill=(230, 180, 20, 255))
    return outline(img)


def icon_sheet():
    """16x16 HUD icons in item-number order: boost, bug, duck, shield, push."""
    sheet = Image.new("RGBA", (16 * 5, 16), CLEAR)
    # Commit Boost: a commit node on a line with an arrow
    img = Image.new("RGBA", (16, 16), CLEAR)
    d = ImageDraw.Draw(img)
    d.rectangle((1, 7, 14, 8), fill=(250, 140, 40, 255))
    d.ellipse((4, 4, 11, 11), fill=(250, 140, 40, 255))
    d.ellipse((6, 6, 9, 9), fill=(255, 236, 200, 255))
    d.polygon(((12, 3), (15, 7), (12, 12)), fill=(255, 214, 60, 255))
    sheet.alpha_composite(outline(img), (0, 0))
    bug = bug_sprite().resize((16, 12), Image.NEAREST)
    sheet.alpha_composite(bug, (16, 2))
    sheet.alpha_composite(duck_sprite(), (32, 1))
    # Copilot Shield: a shield with a sparkle
    img = Image.new("RGBA", (16, 16), CLEAR)
    d = ImageDraw.Draw(img)
    d.polygon(((8, 1), (14, 3), (13, 10), (8, 15), (3, 10), (2, 3)), fill=(80, 170, 255, 255))
    d.polygon(((8, 4), (9, 7), (12, 8), (9, 9), (8, 12), (7, 9), (4, 8), (7, 7)), fill=(255, 255, 255, 255))
    sheet.alpha_composite(outline(img), (48, 0))
    # Force Push: a double arrow pushing forward
    img = Image.new("RGBA", (16, 16), CLEAR)
    d = ImageDraw.Draw(img)
    d.polygon(((1, 3), (8, 8), (1, 13)), fill=(240, 70, 90, 255))
    d.polygon(((7, 3), (14, 8), (7, 13)), fill=(255, 140, 150, 255))
    sheet.alpha_composite(outline(img), (64, 0))
    return sheet


def scenery_sheet(theme):
    """Two upright billboards per theme, 24x32 each."""
    sheet = Image.new("RGBA", (48, 32), CLEAR)
    for n in range(2):
        img = Image.new("RGBA", (24, 32), CLEAR)
        d = ImageDraw.Draw(img)
        if theme == "meadow":
            if n == 0:   # round tree
                d.rectangle((10, 20, 13, 31), fill=(110, 70, 40, 255))
                d.ellipse((2, 2, 21, 24), fill=(40, 130, 60, 255))
                d.ellipse((5, 4, 15, 14), fill=(70, 170, 80, 255))
            else:        # flowering bush
                d.ellipse((1, 18, 22, 31), fill=(46, 140, 64, 255))
                for fx, fy in ((5, 21), (11, 19), (16, 23), (8, 26), (18, 27)):
                    d.ellipse((fx, fy, fx + 2, fy + 2), fill=(255, 220, 240, 255))
        elif theme == "canyon":
            if n == 0:   # cactus
                d.rounded_rectangle((9, 4, 14, 31), 2, fill=(70, 150, 80, 255))
                d.rounded_rectangle((3, 12, 7, 22), 2, fill=(70, 150, 80, 255))
                d.rectangle((5, 20, 9, 22), fill=(70, 150, 80, 255))
                d.rounded_rectangle((16, 8, 20, 18), 2, fill=(70, 150, 80, 255))
                d.rectangle((14, 16, 18, 18), fill=(70, 150, 80, 255))
            else:        # rock pillar
                d.polygon(((4, 31), (6, 8), (12, 2), (18, 6), (20, 31)), fill=(170, 96, 60, 255))
                d.line(((7, 16), (17, 16)), fill=(140, 76, 46, 255))
                d.line(((6, 24), (19, 24)), fill=(140, 76, 46, 255))
        elif theme == "frost":
            if n == 0:   # snowy pine
                d.rectangle((10, 26, 13, 31), fill=(90, 60, 40, 255))
                for top, half in ((2, 6), (8, 8), (14, 10)):
                    d.polygon(((12, top), (12 - half, top + 12), (12 + half, top + 12)), fill=(30, 90, 70, 255))
                    d.polygon(((12, top), (12 - half // 2, top + 5), (12 + half // 2, top + 5)), fill=(250, 250, 255, 255))
            else:        # ice crystal
                d.polygon(((12, 2), (17, 14), (12, 31), (7, 14)), fill=(170, 220, 255, 230))
                d.polygon(((12, 2), (14, 14), (12, 31)), fill=(230, 246, 255, 255))
        else:  # volcano
            if n == 0:   # obsidian spike
                d.polygon(((6, 31), (11, 3), (18, 31)), fill=(40, 30, 50, 255))
                d.line(((11, 6), (14, 30)), fill=(120, 80, 140, 255))
            else:        # glowing rock
                d.ellipse((2, 14, 21, 31), fill=(60, 40, 40, 255))
                d.line(((6, 20), (12, 24), (17, 19)), fill=(255, 150, 40, 255), width=2)
        sheet.alpha_composite(outline(img), (n * 24, 0))
    return sheet


def portraits(side, front):
    sheet = Image.new("RGBA", (CELL * len(side), CELL), CLEAR)
    for i, im in enumerate(side):
        r = crop_alpha(im)
        sheet.alpha_composite(r, (i * CELL + (CELL - r.width) // 2, CELL - r.height - 2))
    return sheet


def trophy():
    img = Image.new("RGBA", (24, 24), CLEAR)
    d = ImageDraw.Draw(img)
    gold, dark = (255, 200, 40, 255), (200, 140, 20, 255)
    d.ellipse((1, 4, 7, 12), outline=gold, width=2)
    d.ellipse((16, 4, 22, 12), outline=gold, width=2)
    d.pieslice((4, -6, 19, 16), 0, 180, fill=gold)
    d.rectangle((10, 15, 13, 19), fill=dark)
    d.rectangle((6, 19, 17, 22), fill=gold)
    d.line(((8, 3), (8, 8)), fill=(255, 246, 200, 255))
    return outline(img)


# --- tracks ------------------------------------------------------------------

def track_texture(spec, rng):
    g = Geometry(spec)
    img = Image.new("RGB", (SIZE, SIZE), spec["ground"][0])
    d = ImageDraw.Draw(img)
    ga, gb = spec["ground"]
    for y in range(0, SIZE, 32):
        for x in range((y // 32) % 2 * 32, SIZE, 64):
            d.rectangle((x, y, x + 31, y + 31), fill=gb)
    key = spec["key"]
    # ground detail
    for _ in range(1400):
        x, y = rng.randrange(SIZE), rng.randrange(SIZE)
        if key == "meadow":
            c = rng.choice(((250, 240, 120), (255, 255, 255), (250, 170, 210), (40, 120, 50)))
            d.point((x, y), fill=c)
        elif key == "canyon":
            c = rng.choice(((190, 140, 76), (226, 186, 120)))
            d.line(((x, y), (x + rng.randint(-3, 3), y + rng.randint(-3, 3))), fill=c)
        elif key == "frost":
            d.point((x, y), fill=rng.choice(((255, 255, 255), (190, 210, 236))))
        else:
            r = rng.randint(1, 4)
            d.ellipse((x - r, y - r, x + r, y + r), fill=rng.choice(((255, 210, 60), (200, 50, 10), (120, 20, 10))))
    pts = g.points
    n = g.count
    road, curb = g.road, g.curb

    # per-waypoint normals (averaged over the two adjacent segments) so the
    # strips join without gaps
    normals = []
    for i in range(n):
        h0 = g.headings[i - 1]
        h1 = g.headings[i]
        hx = math.cos(h0) + math.cos(h1)
        hy = math.sin(h0) + math.sin(h1)
        ln = math.hypot(hx, hy) or 1.0
        normals.append((-hy / ln, hx / ln))

    def band(i, r0, r1, fill):
        a, b = pts[i], pts[(i + 1) % n]
        na, nb = normals[i], normals[(i + 1) % n]
        d.polygon([(a[0] + na[0] * r0, a[1] + na[1] * r0), (b[0] + nb[0] * r0, b[1] + nb[1] * r0),
                   (b[0] + nb[0] * r1, b[1] + nb[1] * r1), (a[0] + na[0] * r1, a[1] + na[1] * r1)], fill=fill)

    # curbs alternate colours every two waypoints, then the tarmac on top
    for i in range(n):
        col = spec["curb_rgb"][(i // 2) % 2]
        band(i, road - 1, road + curb, col)
        band(i, -road + 1, -road - curb, col)
    for i in range(n):
        band(i, -road, road, spec["road_rgb"])
    # asphalt speckle
    rr, rg, rb = spec["road_rgb"]
    for i in range(n):
        for _ in range(10):
            lat = rng.uniform(-road + 1, road - 1)
            x, y = g.place(i, lat)
            x += rng.uniform(-3, 3)
            k = rng.choice((0.88, 1.12))
            d.point((x, y), fill=(int(rr * k), int(rg * k), min(255, int(rb * k))))
    # centre dashes
    dash = (238, 238, 230) if key != "volcano" else (250, 190, 60)
    for i in range(0, n, 4):
        a, b = pts[i], pts[(i + 1) % n]
        d.line((a, b), fill=dash, width=2)
    # ice patches
    for px, py, r in g.patches:
        d.ellipse((px - r, py - r, px + r, py + r), fill=(214, 238, 255))
        d.ellipse((px - r + 3, py - r + 3, px + r - 6, py + r - 6), fill=(236, 248, 255))
    # boost pads: chevrons along the heading
    for px, py, h in g.pads:
        fx, fy = math.cos(h), math.sin(h)
        rx, ry = -fy, fx
        d.polygon([(px + rx * 7 - fx * 7, py + ry * 7 - fy * 7), (px - rx * 7 - fx * 7, py - ry * 7 - fy * 7),
                   (px - rx * 7 + fx * 7, py - ry * 7 + fy * 7), (px + rx * 7 + fx * 7, py + ry * 7 + fy * 7)],
                  fill=(40, 40, 60))
        for k in (-4, 2):
            c = (px + fx * k, py + fy * k)
            d.polygon([(c[0] + fx * 4, c[1] + fy * 4), (c[0] + rx * 5 - fx * 1, c[1] + ry * 5 - fy * 1),
                       (c[0] + rx * 3 - fx * 3, c[1] + ry * 3 - fy * 3), (c[0] + fx * 1, c[1] + fy * 1),
                       (c[0] - rx * 3 - fx * 3, c[1] - ry * 3 - fy * 3), (c[0] - rx * 5 - fx * 1, c[1] - ry * 5 - fy * 1)],
                      fill=(80, 230, 255))
    # chequered start line, two rows across the road
    h = g.headings[0]
    fx, fy = math.cos(h), math.sin(h)
    rx, ry = -fy, fx
    x0, y0 = pts[0]
    for row in range(2):
        for k in range(-int(road), int(road), 3):
            c = (20, 20, 20) if ((k + 99) // 3 + row) % 2 else (250, 250, 250)
            cx = x0 + rx * k + fx * row * 3
            cy = y0 + ry * k + fy * row * 3
            d.polygon([(cx, cy), (cx + rx * 3, cy + ry * 3), (cx + rx * 3 + fx * 3, cy + ry * 3 + fy * 3),
                       (cx + fx * 3, cy + fy * 3)], fill=c)
    # grid slot marks
    for slot in range(4):
        x, y, hh, _i = g.grid_slot(slot)
        bx, by = x + math.cos(hh) * 5, y + math.sin(hh) * 5
        d.line(((bx - math.sin(hh) * 4, by + math.cos(hh) * 4), (bx + math.sin(hh) * 4, by - math.cos(hh) * 4)),
               fill=(240, 240, 240), width=1)
    return img.quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)


def scenery_positions(spec, rng):
    """Billboard spots outside the curbs, kept clear of every part of the road."""
    g = Geometry(spec)
    spots = []
    clear = g.road + g.curb + 7
    for i in range(0, g.count, 5):
        for side in (-1, 1):
            if rng.random() < 0.45:
                continue
            lat = side * (clear + rng.uniform(2, 26))
            x, y = g.place(i, lat)
            if not (8 < x < SIZE - 8 and 8 < y < SIZE - 8):
                continue
            j = g.nearest_global(x, y)
            if abs(g.nearest(x, y, j)[2]) < clear:
                continue
            spots.append((round(x), round(y), rng.randrange(2)))
    return spots


def main():
    OUT.mkdir(exist_ok=True)
    rng = random.Random(2026)
    mona = frames("badge/apps/flappy/assets/mona.png", 24, 24)
    chick = frames("badge/apps/plucky_cluck/assets/chicken.png", 24, 24)
    squirrel = frames("badge/assets/squirrel-sprites/default.png", 32, 32)
    bee_side = frames("badge/apps/bee_amazed/assets/bee-right.png", 16, 16)
    bee_front = frames("badge/apps/bee_amazed/assets/bee-down.png", 16, 16)
    sides = {"mona": mona[6], "cluck": chick[1], "sciuri": squirrel[0],
             "buzz": bee_side[0].resize((24, 24), Image.NEAREST)}
    fronts = {"mona": mona[5], "cluck": chick[5], "sciuri": squirrel[0],
              "buzz": bee_front[0].resize((24, 24), Image.NEAREST)}
    for key in ("tux", "ferris", "gopher", "duke", "droid"):
        sides[key] = eco("side", key)
        fronts[key] = eco("front", key)
    for ch in config.CHARACTERS:
        sheet = kart_sheet(ch, sides[ch["key"]], fronts[ch["key"]])
        sheet.save(OUT / ("kart_%s.png" % ch["key"]))
        sheet.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS).save(
            OUT / ("kart_%s_half.png" % ch["key"]))
    faces = {"mona": mona[0], "cluck": chick[5], "sciuri": squirrel[0],
             "buzz": bee_front[0].resize((24, 24), Image.NEAREST)}
    portraits([faces.get(ch["key"]) or fronts[ch["key"]] for ch in config.CHARACTERS],
              None).save(OUT / "portraits.png")
    item_box_sheet().save(OUT / "box.png")
    bug_sprite().save(OUT / "bug.png")
    duck_sprite().save(OUT / "duck.png")
    icon_sheet().save(OUT / "icons.png")
    trophy().save(OUT / "trophy.png")
    lines = ["# Generated by Team2/make_assets.py; do not edit by hand.", "SCENERY = {"]
    for spec in config.TRACKS:
        track_texture(spec, random.Random(spec["key"])).save(OUT / ("track_%s.png" % spec["key"]), optimize=True)
        scenery_sheet(spec["key"]).save(OUT / ("scenery_%s.png" % spec["key"]))
        spots = scenery_positions(spec, random.Random("s" + spec["key"]))
        lines.append("    %r: %r," % (spec["key"], tuple(spots)))
    lines.append("}")
    (APP / "scenery.py").write_text("\n".join(lines) + "\n")
    for f in sorted(OUT.iterdir()):
        print("%-28s %6d bytes" % (f.name, f.stat().st_size))


if __name__ == "__main__":
    main()
