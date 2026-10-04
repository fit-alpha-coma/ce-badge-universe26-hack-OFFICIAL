# Super Mona Kart: design

A kart racer for the GitHub Universe 2026 badge in which the mascots of the
badge's own apps race each other: Mona (Flappy), Cluck (Plucky Cluck), Sciuri
(Snarky Sciuridae) and Buzz (Bee Amazed). This document records how we got
there, so the team can argue with the reasons rather than the results.

## 1. Empathize: who plays, where, and what gets in their way

| Who | Situation | What they need | What gets in the way |
| --- | --- | --- | --- |
| Judges | Two or three minutes per team, a queue behind them | A "wow" in the first ten seconds, something only this badge can do, polish, no crash | Long menus, unreadable text, a demo that needs explaining |
| Attendees wearing badges | Standing in a hall, badge on a lanyard, thumbs on capacitive pads, one or two minute sessions | Instant play, controls that forgive imprecise touch, playing with the people next to them | No throttle thumb to spare, glare, conference Wi-Fi, typing on a D-pad |
| Our team | Four people, a weekend, one or two physical badges | Code we can test without hardware, nothing that only works on a laptop | A simulator that did not match the firmware (fixed, see section 6) |

Observations from the hardware (`hardware/README.md`, schematic, input test app):

- The touch face is a game pad: a D-pad under the left thumb, SELECT and BACK
  under the right thumb, MENU and HOME between them.
- The physical switches are Left, Right and Select on the bottom row and Up and
  Down on the right edge. There is no physical BACK or MENU, so everything
  essential must also work from the switches.
- Four white case LEDs (CL0 to CL3), driven by PWM through `badge.caselights()`.
- RP2350 at 200 MHz with PicoVector v3.1.0 doing all per-pixel work in C.

## 2. Define

How might we give a crowd of badge wearers a one-minute race that reads at a
glance, feels fair on touch controls, and pulls the person next to them into
the game?

## 3. What makes SuperTuxKart fun, and what survives on a badge

| STK ingredient | Why it works | On the badge |
| --- | --- | --- |
| Skidding with a mini-turbo | Skill you can feel within one corner | Kept: hold BACK (or physical Up) while steering; blue, orange and pink sparks; release to boost |
| Items | Chaos, comebacks, laughs | Kept, five GitHub-themed items, weighted by race position |
| Rubber-band racing | Every race stays close | Kept but capped, and only for computer karts |
| Varied tracks | Each race feels new | Four themed tracks whose surfaces change the driving: grass, sand, ice, lava |
| Distinct characters | Identity and choice | Four mascots with stats that trade off and sum to the same total |
| Grand Prix | A reason to play the next race | Octo Cup: four races, points, podium, trophies saved |
| Time trial | Mastery | Ghost of your best run, three boosts |
| Split screen with friends | The social glue | Party mode: badge to badge over Wi-Fi |

Things we deliberately leave out: a throttle button (no thumb for it, the kart
accelerates on its own), 3D models (sprites at the badge's native resolution
look sharper), and long tracks (laps of 12 to 20 seconds keep a race near a
minute).

## 4. Ideate: the decisions

**Controls** (logical actions, shown on screen with the input test app's own
labels):

| Action | Touch face | Physical switches |
| --- | --- | --- |
| Steer | D-pad LEFT / RIGHT | Left / Right |
| Drift | BACK (right thumb) | Up |
| Use item | SELECT | Select |
| Brake / reverse | D-pad DOWN | Down |
| Pause | MENU | Up + Down together |
| Back in menus | BACK | Left in lists, Up on the racer and track pickers, Up + Down in the party lobby |

HOME always returns to the launcher (the firmware owns it). On-screen prompts
use the input test app's own pad labels (SEL, BK, MN) and show the switch
alternative after a slash, for example "BK/<".

Steering assist (on by default, can be turned off) nudges the kart back toward
the road when no direction is held. Tilt steering is an option.

**Characters** (speed, acceleration, handling, weight; each sums to 12):
Mona 3/3/3/3, Cluck 2/5/3/2, Sciuri 4/2/2/4, Buzz 3/2/5/2.

**Tracks** (Octo Cup, in order): Octocat Meadow (wide, grass), Merge Conflict
Canyon (narrow, deep sand, boost pads), Frost Fork (ice road, low grip, night
sky), Deploy Volcano (lava edges: fall in and you are put back with a delay).

**Items** (STK inspiration in brackets):

| Item | Effect | Weighted toward |
| --- | --- | --- |
| Commit Boost (zipper) | Instant boost | Middle and back |
| Bug (banana / bubblegum) | Dropped behind; spins out whoever hits it | Front |
| Rubber Duck (cake) | Thrown ahead, steers to the next kart | Middle |
| Copilot Shield (bubble) | Absorbs one hit for six seconds | Front and middle |
| Force Push (lightning) | Every kart ahead spins | Last place only |

**Case lights** (subtle, off in menus, can be turned off): countdown lights one
LED per count and all four on GO; a soft glow that rises with the drift charge;
a flash on boost; a double blink when hit; slow breathing on the final lap; a
chase on a win; in the party lobby, one LED per connected badge.

**Fairness**: one physics model for every kart; character stats trade off
evenly; computer rubber-banding is capped; the leader cannot draw attacking
items; in party mode each badge decides whether its own kart was hit.

**Memorable**: the badge's own mascots, Mona Sans for titles (it ships on the
badge in `/system/assets/fonts`), item boxes styled as contribution-graph
squares, GitHub puns, a podium with confetti and the case lights.

## 5. Prototype and test

The first prototype was Tux Kart (single track, three computer karts). It
proved the Mode 7 floor (one `blit_hspan` per row) and exposed physics bugs
that a scripted race caught: karts glued together and a top speed capped by
drag. Super Mona Kart builds on it.

Tests, in the order they run:

1. `Team2/test_super_mona_kart.py`: the race logic (geometry, physics, laps,
   items, standings, points, packets) is plain Python with no graphics, so it
   runs under desktop Python with only the standard library.
2. `Team2/badgesim.py`: scripted runs in the firmware-faithful simulator,
   with screenshots, and two simulators racing each other over UDP.
3. An adversarial review by Codex (gpt-6.1-sol, medium effort) of the code and
   this document; dispositions are logged in section 8.
4. On a physical badge: frame rate (MENU shows it), touch feel, case lights,
   party mode on a phone hotspot.

## 6. Critique of the repository (what we found and what we did)

| Finding | Evidence | Effect | What we did |
| --- | --- | --- | --- |
| Two different control layouts in one document | `hardware/README.md` "Button layout" (five switches) vs the CAP1208 section (eight pads) | Apps could ignore half the controls | Both are real: switches and a touch face map to the same logical actions. The game supports both |
| The app contract recommends `os.path.dirname(__file__)` | `references/app-contract.md` | MicroPython has no `os.path`; the app crashes at import | We use `__file__.rsplit("/", 1)` |
| README lists `badge/apps/contacts` and `badge/apps/pong` as BLE examples | `README.md` table | Neither exists here or upstream, so there is no BLE reference | Party mode uses Wi-Fi UDP |
| `wifi.connect()` calls `fatal_error` (reset) on a missing SSID or a timeout | tufty2350 `modules/common/wifi.py` | A multiplayer menu would reboot the badge | We drive `network.WLAN` directly with our own timeout |
| The emulator docs point at simulators that do not match the firmware | The native simulator links an older PicoVector; the web simulator lacks the 2026 inputs | Code could pass in the simulator and fail on the badge | We rebuilt the native simulator on PicoVector v3.1.0 and the real runtime (below) |
| `input_test` imports `brand`, which is not in the repo | `badge/apps/input_test/__init__.py` | Only runs with the GitHub firmware's frozen module | Noted; the game does not use it |

**Emulation.** The badge firmware is a derivative of `pimoroni/tufty2350`
(commit `ee84772`), which pins PicoVector v3.1.0 and MicroPython
`bw-1.29.0-gc`. Our simulator branch (`pv3-runtime` of
`pimoroni/badgeware-simulator`) links PicoVector v3.1.0 and boots that
firmware's own `badgeware` Python runtime, patched in three asserted places.
Only drivers are stubbed. Unmodified 2026 apps (Plucky Cluck, Tennis, the
demos) run in it. Known gaps: MicroPython 1.26 instead of 1.29, no
`@micropython.native` or `viper` (the game uses neither), and GitHub's own
2026 input layer is emulated from its documentation because its source is not
public.

## 7. Risks

| Risk | Mitigation |
| --- | --- |
| Frame rate on the real RP2350 | The sky and floor render at 160x120 and are scaled up in one blit; Settings can show the frame rate; Fast graphics computes every other floor row (drawn twice) and hides scenery. Slow frames run several short physics steps, so speed does not depend on frame rate |
| Conference Wi-Fi blocks badge-to-badge traffic | Party mode explains this and suggests a phone hotspot; everything else works offline |
| Physical switch mapping (A, B, C = Left, Right, Select) | Taken from the documented bottom-row order; check on the first badge we hold |

## 8. Review log

### Round 1: Codex (gpt-6.1-sol, medium), 2026-10-04, 19 findings

| # | Sev | Finding | Disposition |
| --- | --- | --- | --- |
| 1 | High | `render.py` used `fast` instead of `self.fast` (NameError) | Fixed; the emulator also caught it |
| 2 | High | Finalising results left unfinished karts able to finish again; `None` in a sort | Fixed: `Race.finalize()` marks DNF once; finishers sort before DNFs; test added |
| 3 | High | Party finish times came from unsynchronised clocks; frames over 50 ms lost time | Fixed: hellos carry clocks, the host names a shared countdown start, race time is taken from it; slow frames run substeps |
| 4 | High | `badgesim.py` returned success after a crash | Fixed: exit 1 on `FATAL`, a traceback, or an unfinished headless run |
| 5 | High | Ghost samples grew without bound in every mode | Fixed: recorded only in time trials, until the finish, capped at 6000; test added |
| 6 | Medium | Repeated start messages rebuilt the race | Fixed: race id; a start already accepted is ignored |
| 7 | Medium | No race id or sequence number on state packets | Fixed: race id and per-badge sequence; stale and foreign packets dropped; test added |
| 8 | Medium | A disconnected badge's karts stayed frozen forever | Fixed: silent for 4 s means DNF; its karts leave collisions, items and the screen |
| 9 | Medium | Item broadcasts read the last projectile after the step | Fixed: spawn data captured at use time |
| 10 | Medium | Boxes and projectiles resolved independently per badge | Partly fixed: projectiles have ids and a hit removes them everywhere. Two badges taking one box in the same 66 ms both get an item; accepted as rare and harmless |
| 11 | Medium | Box events accepted from anyone | Fixed: events only from badges in the current race id |
| 12 | Medium | Time trial records shared with item races | Fixed: separate `tt_best` and ghost |
| 13 | Medium | Reversing over the line produced a fake best lap | Fixed: reversing voids the lap's timing; test added |
| 14 | Medium | Pause and party exits needed touch-only MENU/BACK | Fixed: Up + Down chord; prompts show it |
| 15 | Medium | Ghost alpha set on the source image | Fixed: `screen.alpha`, per the v3.1.0 API |
| 16 | Medium | Headless runs use a synthetic clock | Kept by design for deterministic tests; `--realtime` exists, and frame-rate claims are left to the physical badge |
| 17 | Low | Clear records kept ghosts | Fixed: `State.delete` for every ghost |
| 18 | Low | The emulator cannot tell touch from switches or simulate inversion | Accepted and documented: the game uses neither `touched()` nor `upside_down()` |
| 19 | Low | DESIGN overstated the performance controls | Fixed in section 7 |

A separate automated security review flagged that malformed party packets
could raise and reset the badge. Fixed: every field is type- and range-checked
and bad packets are dropped (tests added).
