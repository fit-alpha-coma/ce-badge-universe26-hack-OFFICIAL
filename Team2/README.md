# Team 2 workspace

Put Team 2 apps and project files in this folder. See
[`CONTRIBUTING.md`](../CONTRIBUTING.md) for the team workflow.

Start with [the Copilot quickstart](../docs/COPILOT-QUICKSTART.md). Tell Copilot
to create apps under `Team2/<app-name>` and to leave `badge/apps/` unchanged.

## Tux Kart (`tux_kart/`)

A Mode 7 kart racer in the style of the SNES kart games: Tux against three
computer karts, three laps, on a track painted in code at startup.

| Control | Action |
| --- | --- |
| LEFT / RIGHT | Steer (or tilt the badge; toggle with MENU on the title screen) |
| DOWN | Brake (the kart accelerates on its own) |
| SELECT | Start, resume, race again |
| BACK | Pause; on the pause screen, quit to the title |
| MENU (in a race) | Show the frame rate |

Files:

- `track.py`: the track layout, waypoints, lap and off-road queries, and the
  texture painter.
- `render.py`: the Mode 7 camera. Each floor row is one
  `screen.blit_hspan()` call that samples the track texture in C.
- `kart.py`: kart physics, lap counting, collisions and the computer drivers.
- `art.py`: kart sprites (back, side and front views) drawn with shapes.
- `__init__.py`: game states, HUD and input.

### Status

Tested in Pimoroni's native simulator: the title, countdown, race, pause,
results and a full three-lap race (with Tux on autopilot, all four karts
finished between 40.5 s and 42.0 s). Not yet tested on a physical badge.
Check these first on hardware:

1. Frame rate during a race (MENU). The simulator's clock is fixed at 60 fps,
   so its reading means nothing.
2. That `blit_hspan` exists in the badge firmware with the same arguments as
   the simulator. The firmware's `blit_vspan` does (see
   `badge/apps/30_minutes_to_alpha_centauri`).
3. Tilt steering: the axis (`ax`) and its sign are guesses.

Next: multiplayer over Wi-Fi (UDP on a phone hotspot), with each badge
sending its kart's position about 15 times a second.

### Running it headless in the native simulator

`tuxsim.py` runs any 2026-style app in
[`pimoroni/badgeware-simulator`](https://github.com/pimoroni/badgeware-simulator)
with a small shim for the 2026 names (`badge`, `BUTTON_*`, `run`, `font.*`)
and scripted button presses, and saves screenshots.

Build the headless simulator once:

```sh
git clone https://github.com/pimoroni/badgeware-simulator.git
cd badgeware-simulator
git submodule update --init
(cd lib/micropython && git submodule update --init lib/micropython-lib lib/mbedtls)
# macOS: drop the hard-coded Command Line Tools include, which hides libc++ headers
sed -i '' '/CommandLineTools\/SDKs\/MacOSX.sdk\/usr\/include/d' micropython/CMakeLists.txt
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
cmake -S micropython -B build-headless -DHEADLESS=TRUE
cmake --build build-headless -j8
```

Then, from the repository root:

```sh
BADGEWARE_SIMULATOR=/path/to/badgeware-simulator python3 Team2/tuxsim.py Team2/tux_kart \
    --frames 600 --shots 100,300,599 --press 20-22:SELECT --press 250-330:RIGHT \
    --out /tmp/tux-shots
```

`--press START-END:BUTTON` holds a button for that range of frames (60 frames
per second).

To play with the keyboard, build the windowed simulator too
(`cmake -S micropython -B build && cmake --build build -j8`) and run:

```sh
BADGEWARE_SIMULATOR=/path/to/badgeware-simulator python3 Team2/tuxsim.py Team2/tux_kart --play --up-as MENU
```

The simulator reads only six keys, so they map to the badge like this:

| Key | Badge action | In Tux Kart |
| --- | --- | --- |
| Left / Right arrow | LEFT / RIGHT | Steer |
| Down arrow | DOWN | Brake |
| Space | SELECT | Start, resume, race again |
| H | BACK | Pause, quit to title |
| Up arrow | MENU (with `--up-as MENU`) | Frame rate; steering mode on the title |

P saves a screenshot (copied to `--out` when the window closes) and Esc
reloads the app. The simulator does not model touch, the IMU, Wi-Fi or the
RP2350's speed and memory.
