# Text, panels, control prompts and the race HUD, for the 320x240 screen.

import math
from config import CHARACTERS

W = 320
H = 240
WHITE = None
SHADOW = None
PANEL = None
GOLD = None
DIM = None
ACCENT = None


def init_colors():
    global WHITE, SHADOW, PANEL, GOLD, DIM, ACCENT
    WHITE = color.rgb(255, 255, 255)
    SHADOW = color.rgb(0, 0, 0, 150)
    PANEL = color.rgb(12, 14, 34, 190)
    GOLD = color.rgb(255, 208, 64)
    DIM = color.rgb(170, 176, 200)
    ACCENT = color.rgb(120, 220, 255)


def ordinal(n):
    return str(n) + ("st", "nd", "rd", "th")[min(n, 4) - 1]


def fmt_ms(ms):
    if ms is None:
        return "--:--.--"
    ms = max(0, int(ms))
    s = ms // 1000
    return "%d:%02d.%02d" % (s // 60, s % 60, (ms % 1000) // 10)


def text(msg, x, y, f, pen=None, size=0, shadow=True):
    screen.font = f
    if shadow:
        screen.pen = SHADOW
        if size:
            screen.text(msg, x + 1, y + 1, font_size=size)
        else:
            screen.text(msg, x + 1, y + 1)
    screen.pen = pen or WHITE
    if size:
        screen.text(msg, x, y, font_size=size)
    else:
        screen.text(msg, x, y)


def width(msg, f, size=0):
    screen.font = f
    w, _h = screen.measure_text(msg, font_size=size) if size else screen.measure_text(msg)
    return w


def center(msg, y, f, pen=None, size=0, x0=0, x1=W):
    text(msg, x0 + (x1 - x0 - width(msg, f, size)) / 2, y, f, pen, size)


def heading(msg, y, art, size=20, pen=None, x0=0, x1=W):
    """Mona Sans heading (it ships on the badge); ROM ziplock if it is missing."""
    if art.title_font:
        center(msg, y, art.title_font, pen or GOLD, size=size, x0=x0, x1=x1)
    else:
        center(msg, y, art.big, pen or GOLD, x0=x0, x1=x1)


def label(msg, x, y, art, size=14, pen=None):
    if art.title_font:
        text(msg, x, y, art.title_font, pen, size=size)
    else:
        text(msg, x, y, art.small, pen)


def panel(x, y, w, h, pen=None):
    screen.pen = pen or PANEL
    screen.shape(shape.rounded_rectangle(x, y, w, h, 6))


def pad(label, x, y, f):
    """A small pad glyph like the badge's own: a rounded chip with its label."""
    w = width(label, f) + 8
    screen.pen = color.rgb(255, 255, 255, 40)
    screen.shape(shape.rounded_rectangle(x, y, w, 13, 6))
    screen.pen = color.rgb(255, 255, 255, 200)
    screen.shape(shape.rounded_rectangle(x, y, w, 13, 6))
    screen.pen = color.rgb(20, 22, 40)
    screen.font = f
    screen.text(label, x + 4, y + 1)
    return w


def prompt(pairs, y, f):
    """Centre a row of (pad label, action) prompts, e.g. [("SEL", "race")]."""
    total = 0
    for p, a in pairs:
        total += width(p, f) + 8 + 4 + width(a, f) + 12
    x = (W - total + 12) / 2
    for p, a in pairs:
        x += pad(p, x, y, f) + 4
        text(a, x, y + 1, f, DIM, shadow=False)
        x += width(a, f) + 12


def stat_bars(stats, x, y, f):
    names = ("Speed", "Accel", "Handling", "Weight")
    for i, (n, v) in enumerate(zip(names, stats)):
        text(n, x, y + i * 14, f, DIM, shadow=False)
        for j in range(5):
            screen.pen = ACCENT if j < v else color.rgb(255, 255, 255, 40)
            screen.shape(shape.rounded_rectangle(x + 64 + j * 13, y + i * 14 + 2, 11, 8, 2))


# -- race HUD --------------------------------------------------------------------

def hud(race, kart, art, world, now_ms, laps, show_fps, fps):
    f = art.small
    lap = max(1, min(laps, kart.lap))
    panel(4, 4, 92, 38)
    text("LAP", 10, 8, f, DIM, shadow=False)
    text("%d/%d" % (lap, laps), 36, 6, art.big, WHITE)
    t = kart.finished_ms if kart.finished_ms is not None else max(0, race.clock_ms)
    text(fmt_ms(t), 10, 26, art.small, WHITE)

    place = race.rank_of(kart) + 1
    msg = ordinal(place)
    pen = GOLD if place == 1 else WHITE
    text(msg, W - width(msg, art.big, 2) - 8, 2, art.big, pen, size=2)

    # item slot
    panel(W // 2 - 18, 4, 36, 36)
    if kart.item:
        icon = art.icons[kart.item]
        bob = 1 if (now_ms // 300) % 2 else 0
        screen.blit(icon, rect(W // 2 - 16, 6 + bob, 32, 32))

    # drift charge meter
    if kart.drift:
        cols = ((90, 170, 255), (255, 160, 40), (255, 90, 220))
        lvl = kart.level
        frac = min(1.0, kart.charge / 2.2)
        screen.pen = color.rgb(0, 0, 0, 120)
        screen.shape(shape.rounded_rectangle(W // 2 - 30, 44, 60, 6, 3))
        c = cols[lvl - 1] if lvl else (200, 200, 200)
        screen.pen = color.rgb(*c)
        screen.shape(shape.rounded_rectangle(W // 2 - 30, 44, 60 * frac, 6, 3))

    # minimap with every kart
    mx, my = W - 70, H - 70
    panel(mx - 3, my - 3, 70, 70)
    screen.blit(world.mini, vec2(mx, my))
    for k in race.karts:
        ch = CHARACTERS[k.char]
        screen.pen = color.rgb(*ch["body"])
        r = 3.5 if k is kart else 2.5
        screen.shape(shape.circle(mx + k.x / 8, my + k.y / 8, r))
        if k is kart:
            screen.pen = WHITE
            screen.shape(shape.circle(mx + k.x / 8, my + k.y / 8, 1.5))

    if kart.wrong_way > 1.0 and (now_ms // 300) % 2:
        center("WRONG WAY", 110, art.big, color.rgb(255, 90, 90), size=2)
    elif kart.off_course > 0.6:
        center("BACK TO THE TRACK", 112, art.mid, color.rgb(255, 220, 120))
    if show_fps:
        text("%d fps" % fps, 8, H - 14, f, color.rgb(255, 130, 130))
