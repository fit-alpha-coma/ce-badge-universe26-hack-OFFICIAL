# Unlockable racers. Plain Python, so it is testable on a desktop.

from config import CHARACTERS, TRACKS


def starters():
    return [c["key"] for c in CHARACTERS if not c.get("unlock")]


def unlocked(save):
    keys = set(save.get("unlocked") or ()) | set(starters())
    return [i for i, c in enumerate(CHARACTERS) if c["key"] in keys]


def goals_met(save):
    """Unlock goals reached according to the saved records."""
    met = set()
    cups = save.get("cups") or {}
    if save.get("cup_done"):
        met.add("cup")
    if cups.get("0") == 1:
        met.add("easy")
    if cups.get("1") == 1:
        met.add("normal")
    tt = save.get("tt_best") or {}
    if all(tr["key"] in tt for tr in TRACKS):
        met.add("trials")
    return met


def newly_unlocked(save):
    """Mark racers whose goal is now met; return the names just unlocked."""
    have = set(save.get("unlocked") or ())
    met = goals_met(save)
    fresh = []
    for c in CHARACTERS:
        goal = c.get("unlock")
        if goal and goal in met and c["key"] not in have:
            have.add(c["key"])
            fresh.append(c["name"])
    save["unlocked"] = sorted(have)
    return fresh


def pick_rivals(player, pool, rng, n=3):
    """n different racers from `pool` (character indexes), never the player."""
    choices = [i for i in pool if i != player]
    out = []
    while choices and len(out) < n:
        out.append(choices.pop(rng.randrange(len(choices))))
    return out
