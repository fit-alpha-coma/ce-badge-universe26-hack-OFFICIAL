#!/usr/bin/env python3
"""Run a Universe 2026 badge app in a firmware-faithful simulator.

This drives a build of pimoroni/badgeware-simulator that links the same
PicoVector the badge firmware pins (v3.1.0) and boots the real Tufty 2350
`badgeware` Python runtime, with GitHub's 2026 input additions on top
(branch `pv3-runtime`; see Team2/README.md). Only the hardware drivers are
stubbed: display, switches, touch, IMU, case lights, RTC and Wi-Fi.

Frames follow the firmware's run() loop: badge.clear(), update(),
display.update(), badge.poll(). HOME quits the app as the launcher's
interrupt does.

Examples:

    # play in a window with the keyboard
    python3 Team2/badgesim.py Team2/super_mona_kart --play

    # 10 s headless, hold SELECT for frames 20-22, screenshots at 3 frames
    python3 Team2/badgesim.py Team2/super_mona_kart --frames 600 \
        --press 20-22:SELECT --shots 100,300,599 --out /tmp/shots
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# simulator.buttons bits; LEFT/RIGHT/SELECT are the physical A/B/C switches
BITS = {
    "DOWN": 0x01, "UP": 0x02, "SELECT": 0x04, "RIGHT": 0x08,
    "LEFT": 0x10, "HOME": 0x20, "BACK": 0x40, "MENU": 0x80,
}

BOOT = '''
import sys
sys.path[:0] = ["/stubs", "/firmware"]
'''

MAIN = r'''
import sys, os, gc, builtins, simulator


def update():
    # replaced below once the app is running; exits if boot fails first
    sys.exit(255)


CONFIG = __CONFIG__
simulator.realtime(CONFIG["play"] or CONFIG["realtime"])

import badgeware
import _input


def _fatal(title, error):
    # The firmware shows a dialog, waits for a button and resets; headless
    # runs cannot wait, so print it and stop with a failing status.
    if not isinstance(error, str):
        error = badgeware.get_exception(error)
    print("FATAL:", title)
    print(error)
    sys.exit(255)


builtins.fatal_error = _fatal
badgeware.fatal_error = _fatal

import badge2026
badge2026.tilt[0] = CONFIG["tilt"]

SCRIPT = []
for spec in CONFIG["press"]:
    span, name = spec.split(":")
    a, b = span.split("-")
    SCRIPT.append((int(a), int(b), CONFIG["bits"][name.upper()]))
frame = 0


def _scripted():
    m = 0
    for a, b, bit in SCRIPT:
        if a <= frame < b:
            m |= bit
    return m


_input.script = _scripted if SCRIPT else None

# run(update) on the badge blocks in a loop; here the simulator's C loop calls
# update() below once per frame, so run() only records the callback.
_app = {"fn": None}
_RealRun = run  # a builtins override: visible by name, not as builtins.run


class _SimRun(_RealRun):
    def __call__(self, update):
        badge.poll()
        self.start = badge.ticks
        builtins.loop = self
        _app["fn"] = update


builtins.run = _SimRun
APP = "/system/apps/" + CONFIG["app"]
try:
    os.chdir(APP)
    sys.path.insert(0, APP)
    _module = __import__(APP)
except Exception as e:
    _fatal("Error!", e)
if _app["fn"] is None:
    _fatal("Error!", "the app never called run(update)")
SHOTS = set(CONFIG["shots"])


def update():
    global frame
    badge.clear()
    try:
        result = _app["fn"]()
    except Exception as e:
        _fatal("Error!", e)
    if result is not None:
        print("APP RETURNED", result)
        sys.exit(255)
    display.update()
    if frame in SHOTS:
        simulator.screenshot("frame-%05d" % frame)
    badge.poll()
    frame += 1
    if BUTTON_HOME in badge.pressed():
        on_exit = getattr(_module, "on_exit", None)
        if callable(on_exit):
            on_exit()
        print("HOME: back to the launcher")
        sys.exit(255)
    if not CONFIG["play"] and frame >= CONFIG["frames"]:
        gc.collect()
        print("BADGESIM_FREE", gc.mem_free())
        sys.exit(255)
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("app", type=Path, help="app folder, e.g. Team2/super_mona_kart")
    parser.add_argument("--play", action="store_true", help="open a window and play in real time")
    parser.add_argument("--frames", type=int, default=120, help="headless run length")
    parser.add_argument("--shots", default="", help="comma-separated frame numbers to capture")
    parser.add_argument(
        "--press", action="append", default=[],
        help="FRAME_START-FRAME_END:ACTION, repeatable; ACTION is " + " ".join(BITS),
    )
    parser.add_argument("--tilt", type=float, default=0.0, help="simulated sideways tilt in g")
    parser.add_argument("--out", type=Path, default=Path("badgesim-shots"))
    parser.add_argument("--state", type=Path, help="persist /state here between runs")
    parser.add_argument(
        "--sim", type=Path,
        default=Path(os.environ.get("BADGEWARE_SIMULATOR", Path.home() / "badgeware-simulator")),
        help="badgeware-simulator checkout (default $BADGEWARE_SIMULATOR or ~/badgeware-simulator)",
    )
    parser.add_argument("--realtime", action="store_true",
                        help="headless, but on the wall clock (for two badges talking)")
    parser.add_argument("--port-offset", type=int, default=0,
                        help="multiplayer: which simulated badge this is (0-3)")
    args = parser.parse_args()

    build = "build-pv3" if args.play else "build-pv3-headless"
    binary = args.sim / build / "micropython"
    runtime = args.sim / "runtime2026"
    if not binary.is_file() or not runtime.is_dir():
        print(f"error: need {binary} and {runtime}; see Team2/README.md", file=sys.stderr)
        return 2
    app = args.app.resolve()
    if not (app / "__init__.py").is_file():
        print(f"error: {app} has no __init__.py", file=sys.stderr)
        return 2

    config = {
        "app": app.name, "play": args.play, "frames": args.frames,
        "shots": [int(s) for s in args.shots.split(",") if s],
        "press": args.press, "tilt": args.tilt, "bits": BITS, "realtime": args.realtime,
    }
    with tempfile.TemporaryDirectory(prefix="badgesim-") as tmp:
        work = Path(tmp)
        root = work / "root"
        shutil.copytree(runtime / "stubs", root / "stubs")
        shutil.copytree(runtime / "firmware", root / "firmware",
                        ignore=shutil.ignore_patterns("rom"))
        shutil.copytree(runtime / "firmware" / "rom", root / "rom")
        shutil.copy(runtime / "badge2026.py", root / "stubs" / "badge2026.py")
        shutil.copytree(REPO / "badge" / "assets", root / "system" / "assets")
        shutil.copytree(app, root / "system" / "apps" / app.name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        # Wi-Fi details for the stub network; the simulator never uses real ones
        (root / "secrets.py").write_text(
            'WIFI_SSID = "simulator"\nWIFI_PASSWORD = "simulator"\n'
            f"SIM_BADGE = {args.port_offset}\n"
        )
        if args.state and args.state.is_dir():
            shutil.copytree(args.state, root / "state")
        (root / "boot.py").write_text(BOOT)
        (root / "main.py").write_text(MAIN.replace("__CONFIG__", repr(config)))
        (work / "screenshots").mkdir()
        result = subprocess.run(
            [str(binary)], cwd=work, capture_output=True, text=True,
            timeout=None if args.play else 900,
        )
        noise = ("micropython_init", "badgeware_init", 'Running "', "Hot reload",
                 "badgeware_screenshot")
        for line in (result.stdout + result.stderr).splitlines():
            if line.strip() and not line.startswith(noise):
                print(line)
        if args.state and (root / "state").is_dir():
            if args.state.exists():
                shutil.rmtree(args.state)
            shutil.copytree(root / "state", args.state)
        pngs = sorted((work / "screenshots").glob("*.png"))
        if pngs:
            args.out.mkdir(parents=True, exist_ok=True)
            for png in pngs:
                shutil.copy(png, args.out / png.name)
            print(f"saved {len(pngs)} screenshot(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
