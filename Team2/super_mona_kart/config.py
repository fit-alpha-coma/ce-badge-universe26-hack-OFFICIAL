# Game data: characters, tracks, items and scoring. Plain Python.

# Characters are the mascots of the badge's own apps. Stats are
# (speed, acceleration, handling, weight), 1 to 5, and each sums to 12 so no
# pick is strictly better than another.
CHARACTERS = (
    {"key": "mona", "name": "Mona", "app": "Flappy", "stats": (3, 3, 3, 3),
     "body": (124, 72, 214), "trim": (236, 214, 255), "blurb": "All-rounder"},
    {"key": "cluck", "name": "Cluck", "app": "Plucky Cluck", "stats": (2, 5, 3, 2),
     "body": (226, 58, 52), "trim": (255, 236, 214), "blurb": "Quick off the line"},
    {"key": "sciuri", "name": "Sciuri", "app": "Snarky Sciuridae", "stats": (4, 2, 2, 4),
     "body": (150, 92, 44), "trim": (246, 206, 150), "blurb": "Heavy and fast"},
    {"key": "buzz", "name": "Buzz", "app": "Bee Amazed", "stats": (3, 2, 5, 2),
     "body": (246, 192, 30), "trim": (44, 34, 24), "blurb": "Drift master"},
)

# Tracks of the Octo Cup, in race order.
#   layout  closed loop of control points on a 256 grid (scaled to the 512 world)
#   road    half-width of the tarmac; curb is the stripe outside it
#   off     top speed on the off-road surface; drop=True makes it lava
#   grip    1.0 normal, lower slides (ice)
#   pads    boost pads as (fraction of the lap, lateral offset)
#   patches slippery patches as (fraction of the lap, lateral offset, radius)
#   boxes   fractions of the lap that get a row of three item boxes
TRACKS = (
    {
        "key": "meadow", "name": "Octocat Meadow", "laps": 3,
        "road": 18, "curb": 3, "off": 40, "grip": 1.0,
        "layout": ((40, 186), (38, 120), (54, 62), (100, 34), (160, 38), (210, 64),
                   (222, 118), (196, 156), (148, 146), (116, 170), (146, 206),
                   (112, 228), (62, 222)),
        "pads": ((0.27, 0),),
        "patches": (),
        "boxes": (0.1, 0.42, 0.72),
        "sky": ((86, 150, 236), (186, 222, 250)), "hills": (84, 136, 96), "snow": True,
        "ground": ((70, 162, 70), (58, 142, 58)), "road_rgb": (92, 96, 108),
        "curb_rgb": ((222, 48, 48), (244, 244, 244)), "haze": (160, 200, 180),
    },
    {
        "key": "canyon", "name": "Merge Conflict Canyon", "laps": 3,
        "road": 14, "curb": 2, "off": 26, "grip": 1.0,
        "layout": ((30, 200), (28, 138), (60, 108), (36, 66), (70, 28), (132, 30),
                   (134, 82), (176, 98), (222, 58), (232, 134), (192, 154),
                   (224, 204), (172, 232), (112, 204), (70, 232)),
        "pads": ((0.3, -5), (0.85, 5)),
        "patches": (),
        "boxes": (0.1, 0.45, 0.78),
        "sky": ((226, 136, 70), (250, 214, 150)), "hills": (170, 86, 52), "snow": False,
        "ground": ((214, 168, 98), (200, 152, 84)), "road_rgb": (128, 104, 86),
        "curb_rgb": ((90, 60, 40), (236, 214, 170)), "haze": (240, 196, 140),
    },
    {
        "key": "frost", "name": "Frost Fork", "laps": 3,
        "road": 17, "curb": 3, "off": 34, "grip": 0.55,
        "layout": ((50, 196), (40, 120), (70, 50), (140, 34), (210, 50), (226, 112),
                   (184, 132), (140, 112), (98, 132), (130, 172), (200, 180),
                   (222, 222), (140, 232), (82, 226)),
        "pads": ((0.55, 0),),
        "patches": ((0.2, 4, 12), (0.45, -6, 12), (0.68, 6, 10), (0.9, -4, 12)),
        "boxes": (0.08, 0.4, 0.75),
        "sky": ((14, 20, 54), (60, 84, 140)), "hills": (120, 140, 190), "snow": True,
        "ground": ((226, 236, 246), (206, 220, 236)), "road_rgb": (126, 160, 196),
        "curb_rgb": ((60, 110, 200), (250, 250, 255)), "haze": (150, 170, 210),
    },
    {
        "key": "volcano", "name": "Deploy Volcano", "laps": 3,
        "road": 16, "curb": 4, "off": 30, "grip": 1.0, "drop": True,
        "layout": ((38, 172), (36, 130), (70, 96), (40, 56), (90, 28), (150, 40),
                   (160, 90), (122, 124), (150, 164), (190, 150), (190, 92),
                   (214, 54), (240, 100), (234, 174), (214, 222), (130, 228),
                   (54, 222)),
        "pads": ((0.28, 0), (0.66, 0)),
        "patches": (),
        "boxes": (0.08, 0.4, 0.72),
        "sky": ((40, 10, 20), (120, 40, 30)), "hills": (60, 30, 30), "snow": False,
        "ground": ((236, 90, 20), (252, 150, 30)), "road_rgb": (60, 56, 62),
        "curb_rgb": ((30, 28, 32), (250, 200, 60)), "haze": (150, 60, 40),
    },
)

# Items, STK-inspired and GitHub-themed.
BOOST = 1       # Commit Boost: instant speed boost
BUG = 2         # dropped behind; spins out whoever drives into it
DUCK = 3        # Rubber Duck: thrown ahead, steers toward the next kart
SHIELD = 4      # Copilot Shield: absorbs one hit
PUSH = 5        # Force Push: every kart ahead spins (last place only)

ITEM_NAMES = {BOOST: "Commit Boost", BUG: "Bug", DUCK: "Rubber Duck",
              SHIELD: "Copilot Shield", PUSH: "Force Push"}

# Item odds by race position (1st, 2nd, 3rd, 4th): weights per item.
# The leader gets defence, the back of the pack gets the tools to catch up.
ITEM_ODDS = (
    {BUG: 5, SHIELD: 4, BOOST: 1},
    {BUG: 3, DUCK: 4, SHIELD: 2, BOOST: 2},
    {DUCK: 4, BOOST: 4, SHIELD: 1, BUG: 1},
    {BOOST: 5, DUCK: 3, PUSH: 2},
)

POINTS = (10, 7, 5, 3)

# Computer skill by difficulty: fraction of their own top speed.
DIFFICULTY = (
    {"name": "Easy", "skill": 0.86, "items": 0.5, "care": 0.5},
    {"name": "Normal", "skill": 0.93, "items": 1.0, "care": 0.4},
    {"name": "Hard", "skill": 0.985, "items": 1.0, "care": 0.22},
)
