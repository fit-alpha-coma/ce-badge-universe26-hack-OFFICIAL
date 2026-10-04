import os
import sys

# MicroPython has no os.path; fall back to the deployed location
APP_DIR = __file__.rsplit("/", 1)[0] if "/" in __file__ else "/system/apps/tux_kart"
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

import math
from badgeware import State
from track import Track, SIZE
from render import Camera, W, H
from art import kart_views, SPRITE_W, SPRITE_H
from kart import Kart, Driver, bump, wrap_angle

LAPS = 3
KART_WIDTH = 6.0    # texels; sets how big sprites look

TITLE, COUNTDOWN, RACE, PAUSED, RESULTS = range(5)

ROSTER = (
    # name, kart body, helmet, computer skill
    ("TUX", (40, 110, 230), (250, 200, 30), None),
    ("GNU", (220, 50, 50), (240, 240, 240), 0.95),
    ("BSD", (60, 180, 80), (220, 60, 60), 0.91),
    ("KDE", (240, 170, 30), (40, 90, 200), 0.87),
)

saved = {"best_race_ms": 0, "best_lap_ms": 0, "tilt": False}
State.load("tux_kart", saved)

track = Track()
camera = Camera(track.paint(), SIZE)
# the player starts at the back of the grid and has to fight through
GRID = (3, 0, 1, 2)
karts = [Kart(name, kart_views(body, helmet), track, GRID[i])
         for i, (name, body, helmet, _skill) in enumerate(ROSTER)]
player = karts[0]
drivers = [Driver(k, ROSTER[i][3]) for i, k in enumerate(karts) if ROSTER[i][3]]
# drives Tux on the cool-down lap after the flag
cooldown = Driver(player, 0.5)

# minimap: the track texture shrunk once at startup
MINI = 34
minimap = image(MINI, MINI)
minimap.blit(camera.tex, rect(0, 0, MINI, MINI))

state = TITLE
state_ms = 0
race_start_ms = 0
steer = 0.0
tilt_zero = 0.0
finish_order = []
show_fps = False
fps = 0.0

WHITE = color.rgb(255, 255, 255)
SHADOW = color.rgb(0, 0, 0, 110)
INK = color.rgb(16, 18, 30)
PANEL = color.rgb(10, 14, 30, 170)
GOLD = color.rgb(255, 210, 60)


def set_state(s):
    global state, state_ms
    state = s
    state_ms = badge.ticks


def ordinal(n):
    return str(n) + ("st", "nd", "rd", "th")[min(n, 4) - 1]


def fmt_ms(ms):
    if ms is None:
        return "--:--.-"
    s = ms // 1000
    return "%d:%02d.%d" % (s // 60, s % 60, (ms % 1000) // 100)


def standings():
    return sorted(karts, key=lambda k: (k.finished_ms is None, k.finished_ms or 0, -k.progress()))


def text_center(msg, y, f=None):
    if f:
        screen.font = f
    w, _ = screen.measure_text(msg)
    screen.pen = SHADOW
    screen.text(msg, (W - w) // 2 + 1, y + 1)
    screen.pen = WHITE
    screen.text(msg, (W - w) // 2, y)


def text_shadow(msg, x, y, pen=WHITE):
    screen.pen = SHADOW
    screen.text(msg, x + 1, y + 1)
    screen.pen = pen
    screen.text(msg, x, y)


# --- drawing -----------------------------------------------------------------

def draw_karts():
    visible = []
    for k in karts:
        p = camera.project(k.x, k.y)
        if p is not None:
            visible.append((p[3], k, p))
    visible.sort(key=lambda v: -v[0])
    for _z, k, (sx, sy, s, _) in visible:
        w = KART_WIDTH * s * SPRITE_W / 22
        h = w * SPRITE_H / SPRITE_W
        if w < 2 or sx + w < 0 or sx - w > W:
            continue
        # which side of the kart the camera sees
        bearing = math.atan2(k.y - camera.y, k.x - camera.x)
        view = wrap_angle(k.heading - bearing)
        a = abs(view)
        if a < 0.55:
            sprite, flip = k.views[0], False
        elif a > 2.6:
            sprite, flip = k.views[2], False
        else:
            sprite, flip = k.views[1], view < 0
        screen.pen = SHADOW
        screen.shape(shape.rounded_rectangle(sx - w * 0.45, sy - h * 0.12, w * 0.9, h * 0.22, h * 0.1))
        # small bounce so karts feel alive; more on grass
        bob = 0
        if k.speed > 5:
            bob = (1 if (badge.ticks // (60 if k.offroad else 120)) % 2 else 0) * (1 + k.offroad)
        y0 = sy - h - bob * s * 0.25
        if flip:
            screen.blit(sprite, rect(sx + w / 2, y0, -w, h))
        else:
            screen.blit(sprite, rect(sx - w / 2, y0, w, h))


def draw_minimap():
    x0 = W - MINI - 3
    y0 = H - MINI - 3
    screen.pen = PANEL
    screen.rectangle(x0 - 1, y0 - 1, MINI + 2, MINI + 2)
    screen.blit(minimap, vec2(x0, y0))
    for k in reversed(karts):
        screen.pen = color.rgb(*ROSTER[karts.index(k)][1])
        screen.circle(x0 + k.x * MINI / SIZE, y0 + k.y * MINI / SIZE, 2 if k is player else 1.5)


def draw_hud(now):
    screen.font = font.nope
    lap = max(1, min(LAPS, player.lap))
    text_shadow("LAP %d/%d" % (lap, LAPS), 3, 2)
    clock = state_ms if state == PAUSED else now
    elapsed = (player.finished_ms or clock) - race_start_ms if state != COUNTDOWN else 0
    text_shadow(fmt_ms(elapsed), 3, 12)
    place = standings().index(player) + 1
    screen.font = font.ziplock
    msg = ordinal(place)
    w, _ = screen.measure_text(msg)
    text_shadow(msg, W - w - 3, 1, GOLD if place == 1 else WHITE)
    draw_minimap()
    if player.offroad and state == RACE:
        screen.font = font.nope
        text_shadow("GRASS!", 3, H - 11, color.rgb(180, 255, 140))


def draw_world(now):
    camera.follow(player.x, player.y, player.heading)
    camera.draw()
    draw_karts()


# --- states ------------------------------------------------------------------

def new_race():
    global finish_order, steer
    for i, k in enumerate(karts):
        k.reset(GRID[i])
    finish_order = []
    steer = 0.0
    set_state(COUNTDOWN)


def read_steer(dt):
    global steer, tilt_zero
    if saved["tilt"]:
        ax, ay, az, _gx, _gy, _gz = badge.imu()
        g = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
        target = (ax / g - tilt_zero) / 0.35
        target = -1.0 if target < -1 else (1.0 if target > 1 else target)
        if badge.held(BUTTON_LEFT) or badge.held(BUTTON_RIGHT):
            target = badge.held(BUTTON_RIGHT) - badge.held(BUTTON_LEFT)
        steer = target
        return steer
    target = badge.held(BUTTON_RIGHT) - badge.held(BUTTON_LEFT)
    # ease towards full lock so taps make small corrections
    rate = 7.0 * dt
    if steer < target:
        steer = min(target, steer + rate)
    elif steer > target:
        steer = max(target, steer - rate)
    return steer


def calibrate_tilt():
    global tilt_zero
    ax, ay, az, _gx, _gy, _gz = badge.imu()
    g = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
    tilt_zero = ax / g


def step_race(dt, now, racing):
    gap_ref = player.progress()
    for d in drivers + [cooldown]:
        k = d.kart
        if k.finished_ms is not None:
            s, _t, _b = d.control(now, 0, karts)
            k.drive(dt, s, 0.45, 0)
        elif racing and d is not cooldown:
            s, t, b = d.control(now, k.progress() - gap_ref, karts)
            k.drive(dt, s, t, b)
    if racing and player.finished_ms is None:
        braking = badge.held(BUTTON_DOWN)
        player.drive(dt, read_steer(dt), 0 if braking else 1, 1 if braking else 0)
    bump(karts)
    for k in karts:
        if k.locate(now) and k.lap > LAPS and k.finished_ms is None:
            k.finished_ms = now
            finish_order.append(k)


def finish_player(now):
    race_ms = player.finished_ms - race_start_ms
    if not saved["best_race_ms"] or race_ms < saved["best_race_ms"]:
        saved["best_race_ms"] = race_ms
    if player.best_lap_ms and (not saved["best_lap_ms"] or player.best_lap_ms < saved["best_lap_ms"]):
        saved["best_lap_ms"] = player.best_lap_ms
    State.save("tux_kart", saved)


def title(now, dt):
    # attract mode: fly the camera around the track
    pos = (now / 1000 * 9) % track.count
    i = int(pos)
    a = track.points[i]
    b = track.points[(i + 1) % track.count]
    t = pos - i
    h = track.heading_at(i)
    camera.follow(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, h)
    camera.draw()
    draw_karts()
    screen.pen = PANEL
    screen.rectangle(0, 30, W, 62)
    text_center("TUX KART", 34, font.ziplock)
    screen.font = font.nope
    if (now // 500) % 2:
        text_center("SELECT to race", 56)
    text_center(("Tilt" if saved["tilt"] else "Pad") + " steering: MENU", 68)
    text_center("Best " + fmt_ms(saved["best_race_ms"] or None) + "  Lap " + fmt_ms(saved["best_lap_ms"] or None), 80)
    if badge.pressed(BUTTON_MENU):
        saved["tilt"] = not saved["tilt"]
        State.save("tux_kart", saved)
    if badge.pressed(BUTTON_SELECT):
        if saved["tilt"]:
            calibrate_tilt()
        new_race()


def countdown(now, dt):
    global race_start_ms
    step_race(dt, now, False)
    draw_world(now)
    draw_hud(now)
    left = 3 - (now - state_ms) // 900
    text_center(str(left) if left > 0 else "GO!", 44, font.ziplock)
    if left <= 0:
        race_start_ms = now
        set_state(RACE)


def race(now, dt):
    step_race(dt, now, True)
    draw_world(now)
    draw_hud(now)
    if now - race_start_ms < 700:
        text_center("GO!", 44, font.ziplock)
    if player.finished_ms is not None:
        finish_player(now)
        set_state(RESULTS)
        return
    if player.lap == LAPS and player.lap_start_ms and now - player.lap_start_ms < 1500:
        text_center("FINAL LAP", 44, font.ziplock)
    if badge.pressed(BUTTON_BACK):
        set_state(PAUSED)


def paused(now, dt):
    draw_world(now)
    draw_hud(now)
    screen.pen = PANEL
    screen.rectangle(20, 38, W - 40, 44)
    text_center("PAUSED", 42, font.ziplock)
    screen.font = font.nope
    text_center("SELECT resume", 60)
    text_center("BACK quit to title", 70)
    if badge.pressed(BUTTON_SELECT):
        resume(now)
    elif badge.pressed(BUTTON_BACK):
        set_state(TITLE)


def resume(now):
    # leave the paused time out of the race clock and the lap times
    global race_start_ms
    paused_for = now - state_ms
    race_start_ms += paused_for
    for k in karts:
        if k.lap_start_ms is not None:
            k.lap_start_ms += paused_for
    set_state(RACE)


def results(now, dt):
    step_race(dt, now, True)
    draw_world(now)
    screen.pen = PANEL
    screen.rectangle(14, 14, W - 28, 92)
    place = finish_order.index(player) + 1
    text_center("FINISH! " + ordinal(place), 17, font.ziplock)
    screen.font = font.nope
    y = 38
    for i, k in enumerate(standings()):
        t = fmt_ms(k.finished_ms - race_start_ms) if k.finished_ms else "racing"
        pen = GOLD if k is player else WHITE
        text_shadow("%d %s" % (i + 1, k.name), 24, y, pen)
        text_shadow(t, 92, y, pen)
        y += 10
    text_center("Best lap " + fmt_ms(player.best_lap_ms), 80)
    if now - state_ms > 1000:
        text_center("SELECT again  BACK title", 92)
        if badge.pressed(BUTTON_SELECT):
            new_race()
        elif badge.pressed(BUTTON_BACK):
            set_state(TITLE)


STATES = (title, countdown, race, paused, results)


def update():
    global show_fps, fps
    now = badge.ticks
    dt = badge.ticks_delta / 1000
    if dt > 0.05:
        dt = 0.05
    STATES[state](now, dt)
    if state != TITLE and badge.pressed(BUTTON_MENU):
        show_fps = not show_fps
    if show_fps and state != TITLE:
        if badge.ticks_delta:
            fps += (1000 / badge.ticks_delta - fps) * 0.1
        screen.font = font.nope
        text_shadow("%d fps" % fps, 3, 22, color.rgb(255, 120, 120))


run(update)
