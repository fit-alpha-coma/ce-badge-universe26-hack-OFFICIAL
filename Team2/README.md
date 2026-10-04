# Team 2 workspace

Put Team 2 apps and project files in this folder. See
[`CONTRIBUTING.md`](../CONTRIBUTING.md) for the team workflow.

Start with [the Copilot quickstart](../docs/COPILOT-QUICKSTART.md). Tell Copilot
to create apps under `Team2/<app-name>` and to leave `badge/apps/` unchanged.

# Super Mona Kart

The badge mascots' Grand Prix: a Mode 7 kart racer for the GitHub Universe
2026 badge. Mona (Flappy), Cluck (Plucky Cluck), Sciuri (Snarky Sciuridae),
Buzz (Bee Amazed) and Tux race from the start; Ferris, the Go gopher, Duke and
the Android robot unlock as you play. Four tracks (grass, deep sand, ice,
lava), drifting with a mini-turbo, five items, a Grand Prix with a podium, a
time trial against your ghost, and party races between badges over Wi-Fi.
The case lights count down the start, glow with your drift charge and flash
when you boost or get hit.

Why it is built this way, and every review finding: [`DESIGN.md`](DESIGN.md).

## Contents

1. [Quick start](#1-quick-start)
2. [Controls](#2-controls)
3. [Setup](#3-setup)
4. [Reproduce every check](#4-reproduce-every-check)
5. [Rerun one thing](#5-rerun-one-thing)
6. [Put it on a badge](#6-put-it-on-a-badge)
7. [Party races on real badges](#7-party-races-on-real-badges)
8. [Change the art or a track](#8-change-the-art-or-a-track)
9. [Troubleshooting](#9-troubleshooting)
10. [Project layout](#10-project-layout)
11. [Racers and credits](#11-racers-and-credits)

## 1. Quick start

From the repository root, on macOS with Xcode's command line tools, CMake and
Python 3:

```sh
Team2/setup_simulator.sh                                  # once, about 3 minutes
python3 Team2/badgesim.py Team2/super_mona_kart --play    # play with the keyboard
Team2/run_checks.sh                                       # rerun every check
```

Without the simulator you can still run the logic tests and validators
(`Team2/run_checks.sh` skips the emulator steps).

## 2. Controls

On the badge, every action works from the touch face and from the physical
switches:

| Action | Touch face | Physical switches | Simulator keyboard |
| --- | --- | --- | --- |
| Steer | D-pad LEFT / RIGHT | Left / Right | Left / Right arrow (or A / D) |
| Drift (hold, steer, release for a boost) | BACK | Up | Z or Backspace, or Up arrow (W) |
| Use item | SELECT | Select | Space, Enter or X |
| Brake / reverse | D-pad DOWN | Down | Down arrow (S) |
| Pause | MENU | hold Up + Down | M or Tab |
| Back in menus | BACK | Left in lists, Up on the racer and track pickers | Backspace / Z, Left, Up |
| Quit to the launcher | HOME | Home | H (closes the window) |

The kart accelerates by itself. On-screen prompts use the input test app's pad
labels (SEL, BK, MN) and show the switch alternative after a slash.

In the simulator window the four corners glow with the case lights, and P
saves a screenshot.

## 3. Setup

### What you need

| Tool | Used for | Install (macOS) |
| --- | --- | --- |
| Python 3.10+ | everything | python.org or Homebrew |
| git, CMake 3.13+, a C/C++ compiler | the simulator | `xcode-select --install`, `brew install cmake` |
| Pillow (optional) | regenerating art | `python3 -m pip install pillow` |
| `mpremote` (optional) | serial access to a badge | `python3 -m pip install mpremote` |

The game itself needs nothing extra: it is MicroPython that runs on the
badge's firmware.

### The simulator

The stock simulators do not match the badge. The badge firmware is a
derivative of `pimoroni/tufty2350`, which pins PicoVector v3.1.0; the native
simulator links an older PicoVector, and the web simulator lacks the 2026
controls. `Team2/setup_simulator.sh` builds one that matches, from pinned
commits:

| Input | Pinned at | Why |
| --- | --- | --- |
| `pimoroni/badgeware-simulator` | `fddeb7f` | window, headless runner, MicroPython v1.28.0 |
| `Team2/badgesim.patch` | this repo | PicoVector v3.1.0 build, 2026 keys, case lights, driver stubs, 2026 input layer |
| `pimoroni/picovector-micropython` | `1338077` (tag v3.1.0) | the graphics library the badge firmware pins |
| `pimoroni/tufty2350` | `ee84772` | the firmware's own `badgeware` runtime and ROM fonts |

```sh
Team2/setup_simulator.sh                    # into ~/badgeware-simulator
Team2/setup_simulator.sh ~/somewhere/else   # elsewhere; then
export BADGEWARE_SIMULATOR=~/somewhere/else
```

It refuses to overwrite an existing directory. To rebuild from scratch, delete
the directory and run it again. Build logs are `build-pv3.log` and
`build-pv3-headless.log` inside it.

What the simulator emulates, and what it does not:

- Real: PicoVector v3.1.0 drawing, the firmware's `badgeware` runtime (run
  loop, `State`, fonts, `badge.mode`), MicroPython's language and its sort,
  UDP sockets (two simulators can race).
- Emulated from documentation: GitHub's 2026 inputs (`BUTTON_LEFT/RIGHT/SELECT`
  are the physical A/B/C switches, `BACK`/`MENU` are touch-only, `touched`,
  `direction`, `imu`), case lights, Wi-Fi.
- Not modelled: the RP2350's speed and memory, touch feel, the real IMU,
  `@micropython.native`/`viper` (the game uses neither), screen inversion.
  Frame rate must be judged on a badge.

## 4. Reproduce every check

```sh
Team2/run_checks.sh                 # about 40 s; logs and screenshots in /tmp/smk-checks
Team2/run_checks.sh ~/smk-run-1     # or somewhere you choose
```

| Step | What it proves | Needs |
| --- | --- | --- |
| 1 | 43 logic tests: track geometry, physics, drift, laps, shortcut protection, lava, items, AI, standings, Grand Prix points, unlocks, traits, party packet validation | Python |
| 2 | the repository's app and team validators pass | Python |
| 3 | the art regenerates byte-for-byte from `make_assets.py` | Pillow |
| 4 | unmodified 2026 badge apps (Plucky Cluck, Tennis, demos) run in the simulator, so the emulation is trustworthy | simulator |
| 5 | boot, Grand Prix menus, countdown and racing | simulator |
| 6 | physical switches only: back out, Time Trial, hold Up+Down to pause | simulator |
| 7 | two simulated badges find each other, start together and race over UDP | simulator |

Each step prints PASS, FAIL or SKIP, and the script exits 1 on any failure.
Measured on an Apple-silicon Mac (2026-10-05): setup 2.5 minutes from an empty
directory, all ten checks passing in 36 seconds.
Screenshots of every scripted run land in the output directory, one folder per
step.

## 5. Rerun one thing

```sh
# logic tests, verbose, or one class
python3 -m unittest Team2/test_super_mona_kart.py -v
python3 -m unittest Team2.test_super_mona_kart.LapTests -v

# validators
python3 .github/skills/badge-app-builder/scripts/validate_app.py Team2/super_mona_kart
python3 .github/skills/badge-app-builder/scripts/validate_submissions.py Team2

# play, keeping saves (records, unlocks, ghosts) between sessions
python3 Team2/badgesim.py Team2/super_mona_kart --play --state ~/.smk-state

# a scripted headless run: hold ACTION from frame START to END (60 frames a second)
python3 Team2/badgesim.py Team2/super_mona_kart --frames 600 \
    --press 30-32:SELECT --press 60-62:SELECT --shots 100,300,599 --out /tmp/shots
# actions: UP DOWN LEFT RIGHT SELECT BACK MENU HOME; --tilt 0.3 simulates tilting

# two badges racing on one machine, in windows
python3 Team2/badgesim.py Team2/super_mona_kart --play --port-offset 0 &
python3 Team2/badgesim.py Team2/super_mona_kart --play --port-offset 1 &
```

`badgesim.py` exits 1 if the app crashes (a `FATAL` or traceback) or a headless
run stops early, so it works in scripts. `--realtime` runs headless on the wall
clock, which two badges talking to each other need.

## 6. Put it on a badge

1. Connect the badge with a data USB-C cable and double-press RESET for USB
   disk mode; a `BADGER` volume appears.
2. Preview, then copy (the script never copies `secrets.py` or caches):

   ```sh
   python3 .github/skills/badge-app-builder/scripts/deploy_app.py Team2/super_mona_kart
   python3 .github/skills/badge-app-builder/scripts/deploy_app.py Team2/super_mona_kart --write
   # already installed? --replace keeps the old copy as a timestamped backup
   python3 .github/skills/badge-app-builder/scripts/deploy_app.py Team2/super_mona_kart --write --replace
   ```

3. Eject the volume, press RESET once, and pick Super Mona Kart in the menu.

Check on the badge, in this order: Settings > Show frame rate during a race
(if it is low, Settings > Fast graphics); that Left, Right and Select are the
bottom-row switches; drifting with BACK and with Up; the case lights during
the countdown; Settings > Tilt steering.

## 7. Party races on real badges

1. On every badge, set `WIFI_SSID` and `WIFI_PASSWORD` in `secrets.py` (USB
   disk mode, root of the volume). Never commit it.
2. Use a password-protected phone hotspot. Conference Wi-Fi often blocks
   badges talking to each other, and the hotspot password is what keeps
   strangers out of your race.
3. Everyone opens Party. The badge with the lowest id hosts (marked *), picks
   the track with Up/Down and starts with SELECT once two or more badges show.
   Empty slots get computer karts. The case lights show how many badges are in
   the lobby.

A badge that goes quiet for four seconds is out of the race (DNF). Over USB
serial, `party: race ...` is printed when a race starts.

## 8. Change the art or a track

Art and tracks are generated, not hand-edited:

```sh
python3 Team2/make_assets.py    # needs Pillow; rewrites super_mona_kart/assets and scenery.py
python3 -m unittest Team2/test_super_mona_kart.py
```

- Tracks are in `super_mona_kart/config.py` (`TRACKS`): control points on a
  256 grid, road width, surface, boost pads, ice patches and item boxes. The
  tests refuse a layout whose roads overlap, a start on a curve, or a lap
  outside 1200 to 2100 units.
- Characters are in `config.py` (`CHARACTERS`): stats must sum to 12, or 11
  with a trait. New racers need art in `make_assets.py` and a credit if they
  are someone else's mascot.
- Commit the regenerated files with the change; step 3 of `run_checks.sh`
  fails if they drift.

## 9. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `error: need .../build-pv3-headless/micropython` | Run `Team2/setup_simulator.sh`, or set `BADGEWARE_SIMULATOR` to where you built it |
| Build fails with `<cstdlib> tried including <stdlib.h>` | The patch did not apply; rerun the setup into a fresh directory |
| The window shows nothing or closes at once | Run the same command without `--play` for the traceback, or read the printed `FATAL:` lines |
| A party test hangs, or a simulated badge sees nobody | An old simulator may still hold the port: `pkill -f build-pv3`, then rerun |
| Party says "No Wi-Fi details" on a badge | Set `WIFI_SSID`/`WIFI_PASSWORD` in the badge's `secrets.py` |
| Party lobby shows only you on real badges | The network blocks peer traffic; use a phone hotspot |
| The racer you want is a "?" | It is locked; see section 11, or Settings > Unlock all racers (demo) |

## 10. Project layout

| Path | What it is |
| --- | --- |
| `super_mona_kart/` | The app, deployed to `/system/apps/super_mona_kart` |
| `super_mona_kart/geom.py`, `physics.py`, `items.py`, `ai.py`, `race.py`, `progress.py`, `config.py`, `rng.py` | Race logic, plain Python, tested on a desktop |
| `super_mona_kart/render.py`, `ui.py`, `art.py`, `lights.py`, `controls.py`, `game.py` | Drawing, HUD, assets, case lights, input, screens |
| `super_mona_kart/party.py`, `net.py` | Party races over UDP |
| `super_mona_kart/assets/`, `scenery.py` | Generated by `make_assets.py` |
| `super_mona_kart/NOTICES.txt` | Third-party character notices (ships with the app) |
| `test_super_mona_kart.py` | Logic tests |
| `badgesim.py` | Runs any 2026 app in the simulator (window or scripted) |
| `setup_simulator.sh`, `badgesim.patch` | Builds the simulator from pinned upstream commits |
| `run_checks.sh` | Reruns every check |
| `make_assets.py` | Generates the art and tracks |
| `DESIGN.md` | Design thinking, repository critique, emulation notes, review log |

## 11. Racers and credits

| Racer | From | Stats (spd/acc/hnd/wgt) | Unlock |
| --- | --- | --- | --- |
| Mona | Flappy | 3/3/3/3 | start |
| Cluck | Plucky Cluck | 2/5/3/2 | start |
| Sciuri | Snarky Sciuridae | 4/2/2/4 | start |
| Buzz | Bee Amazed | 3/2/5/2 | start |
| Tux | Linux | 2/3/3/3 + grips on ice | start |
| Ferris | Rust | 2/3/2/5 | finish any cup |
| Gopher | Go | 3/4/2/2 + digs through grass | win on Easy |
| Duke | Java | 4/3/3/2 | win on Normal |
| Android robot | Android | 3/3/2/4 | time trial record on every track |

Settings > Unlock all racers (demo) opens the whole roster for a booth.

The open-source mascots are original pixel art based on: Tux by Larry Ewing
(made with The GIMP; use and modification permitted with acknowledgement),
Ferris the Rustacean by Karen Rustad Tolva (CC0), the Go gopher by Renee
French (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/) and Duke
(open-sourced by Sun under the New BSD license). The Android robot is
reproduced or modified from work created and shared by Google and used
according to terms described in the Creative Commons 3.0 Attribution License
(https://creativecommons.org/licenses/by/3.0/). Every racer above is redrawn
as pixel art. Full notices with sources: `super_mona_kart/NOTICES.txt`, also
summarised in Settings > Credits. Git has no mascot character, and GitHub's
other Octodex characters are left out because their terms restrict use.
