#!/usr/bin/env python3
"""Run a Universe 2026 badge app headless in Pimoroni's native simulator.

The native simulator (github.com/pimoroni/badgeware-simulator) runs the real
PicoVector graphics library, but it still exposes the older Tufty API (`io`,
buttons A/B/C). This script adds a small shim that provides the 2026 names an
app expects (`badge`, `BUTTON_*`, `run`, `font.<name>`), then runs the app for
a fixed number of frames on the simulator's deterministic 60 fps clock.

It is a development aid only. It does not prove touch, IMU, wireless, memory
or real RP2350 speed. See Team2/README.md for building the simulator.

Example:

    python3 Team2/tuxsim.py Team2/tux_kart --frames 600 \
        --shots 60,300,599 --press 120-400:RIGHT --out /tmp/shots
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SHIM = r'''
import sys, builtins, simulator, picovector, gc

CONFIG = __CONFIG__
PLAY = CONFIG["play"]
simulator.realtime(PLAY)

BUTTON_UP, BUTTON_DOWN, BUTTON_LEFT, BUTTON_RIGHT = 1, 2, 3, 4
BUTTON_SELECT, BUTTON_BACK, BUTTON_MENU, BUTTON_HOME = 5, 6, 7, 8
NAMES = {"UP": 1, "DOWN": 2, "LEFT": 3, "RIGHT": 4,
         "SELECT": 5, "BACK": 6, "MENU": 7, "HOME": 8}
for _k, _v in NAMES.items():
    setattr(builtins, "BUTTON_" + _k, _v)

# Simulator keys: Left arrow = A, Space = B, Right arrow = C.
IO_MAP = {io.BUTTON_A: BUTTON_LEFT, io.BUTTON_C: BUTTON_RIGHT,
          io.BUTTON_B: BUTTON_SELECT, io.BUTTON_UP: NAMES[CONFIG["up_as"]],
          io.BUTTON_DOWN: BUTTON_DOWN, io.BUTTON_HOME: BUTTON_BACK}

SCRIPT = []
for _spec in CONFIG["press"]:
    _span, _name = _spec.split(":")
    _a, _b = _span.split("-")
    SCRIPT.append((int(_a), int(_b), NAMES[_name.upper()]))


class Badge:
    def __init__(self):
        self.ticks = 0
        self.ticks_delta = 0
        self.default_clear = color.rgb(0, 0, 0)
        self._held = set()
        self._prev = set()
        self.tilt = CONFIG.get("tilt", 0.0)

    def _poll(self, frame):
        io.poll()
        held = set(IO_MAP[b] for b in io.held if b in IO_MAP)
        for a, b, btn in SCRIPT:
            if a <= frame < b:
                held.add(btn)
        self._prev = self._held
        self._held = held

    def pressed(self, b=None):
        s = self._held - self._prev
        return s if b is None else b in s

    def held(self, b=None):
        return set(self._held) if b is None else b in self._held

    def released(self, b=None):
        s = self._prev - self._held
        return s if b is None else b in s

    def touched(self, b=None):
        return self.held(b)

    def direction(self):
        x = (BUTTON_RIGHT in self._held) - (BUTTON_LEFT in self._held)
        y = (BUTTON_DOWN in self._held) - (BUTTON_UP in self._held)
        return vec2(x, y)

    def imu(self):
        # Badge held flat, tilted left or right by CONFIG["tilt"] g.
        return (self.tilt, 0.0, 1.0, 0.0, 0.0, 0.0)

    def mode(self, m):
        mode(m)

    def upside_down(self):
        return False


class Fonts:
    def __init__(self):
        self._cache = {}

    def __getattr__(self, name):
        if name not in self._cache:
            self._cache[name] = pixel_font.load("/system/assets/fonts/%s.ppf" % name)
        return self._cache[name]


builtins.badge = Badge()
builtins.font = Fonts()
_app = {"update": None}


def run(update, init=None, on_exit=None):
    _app["update"] = update
    if init:
        init()


builtins.run = run
builtins.file_exists = lambda p: _exists(p)


def _exists(p):
    import os
    try:
        os.stat(p)
        return True
    except OSError:
        return False


sys.path.insert(0, "/system/apps")
try:
    __import__(CONFIG["app"])
except Exception as e:
    sys.print_exception(e)
    sys.exit(255)
frame = 0
SHOTS = set(CONFIG["shots"])


def update():
    global frame
    if PLAY:
        badge.ticks = io.ticks
        badge.ticks_delta = io.ticks_delta
    else:
        badge.ticks = int(frame * 1000 / 60)
        badge.ticks_delta = 16 if frame else 0
    badge._poll(frame)
    screen.pen = badge.default_clear
    screen.clear()
    try:
        _app["update"]()
    except Exception as e:
        sys.print_exception(e)
        sys.exit(255)
    if frame in SHOTS:
        simulator.screenshot("frame-%05d" % frame)
    frame += 1
    if not PLAY and frame >= CONFIG["frames"]:
        print("TUXSIM_FREE", gc.mem_free())
        sys.exit(255)
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("app", type=Path, help="app folder, e.g. Team2/tux_kart")
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--shots", default="", help="comma-separated frame numbers")
    parser.add_argument(
        "--press",
        action="append",
        default=[],
        help="FRAME_START-FRAME_END:BUTTON, repeatable (UP DOWN LEFT RIGHT SELECT BACK MENU)",
    )
    parser.add_argument("--tilt", type=float, default=0.0, help="simulated IMU x tilt in g")
    parser.add_argument(
        "--play",
        action="store_true",
        help="open the simulator window and play with the keyboard in real time",
    )
    parser.add_argument(
        "--up-as",
        default="UP",
        choices=["UP", "MENU", "BACK", "SELECT"],
        help="badge action sent by the Up arrow (the simulator has only six keys)",
    )
    parser.add_argument("--out", type=Path, default=Path("tuxsim-shots"))
    parser.add_argument(
        "--sim",
        type=Path,
        default=Path(os.environ.get("BADGEWARE_SIMULATOR", "")),
        help="badgeware-simulator checkout with build-headless/ (or $BADGEWARE_SIMULATOR)",
    )
    args = parser.parse_args()

    binary = args.sim / ("build" if args.play else "build-headless") / "micropython"
    if not binary.is_file():
        print(f"error: simulator binary not found at {binary}", file=sys.stderr)
        return 2
    app = args.app.resolve()
    if not (app / "__init__.py").is_file():
        print(f"error: {app} has no __init__.py", file=sys.stderr)
        return 2

    config = {
        "app": app.name,
        "frames": args.frames,
        "shots": [int(s) for s in args.shots.split(",") if s],
        "press": args.press,
        "tilt": args.tilt,
        "play": args.play,
        "up_as": args.up_as,
    }
    with tempfile.TemporaryDirectory(prefix="tuxsim-") as tmp:
        work = Path(tmp)
        shutil.copytree(args.sim / "root", work / "root")
        shutil.copytree(app, work / "root" / "system" / "apps" / app.name)
        (work / "screenshots").mkdir()
        (work / "root" / "main.py").write_text(
            SHIM.replace("__CONFIG__", repr(config))
        )
        result = subprocess.run(
            [str(binary)],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=None if args.play else 600,
        )
        noise = ("micropython_init", "badgeware_init", "Running \"", "Hot reload")
        for line in (result.stdout + result.stderr).splitlines():
            if line.strip() and not line.startswith(noise):
                print(line)
        args.out.mkdir(parents=True, exist_ok=True)
        for png in sorted((work / "screenshots").glob("*.png")):
            shutil.copy(png, args.out / png.name)
            print(f"saved {args.out / png.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
