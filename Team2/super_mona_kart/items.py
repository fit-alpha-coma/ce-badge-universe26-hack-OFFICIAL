# Item boxes, item rolls and the things items put on the track. Plain Python.

import math
from config import BOOST, BUG, DUCK, SHIELD, PUSH, ITEM_ODDS

BOX_RADIUS = 6.0
BOX_RESPAWN = 3.0
BOX_LANES = (-9.0, 0.0, 9.0)
BUG_RADIUS = 5.0
BUG_LIFE = 30.0
DUCK_SPEED = 150.0
DUCK_RADIUS = 6.0
DUCK_LIFE = 6.0
SHIELD_TIME = 6.0
BOOST_TIME = 1.1
OWNER_GRACE = 0.6


def roll(rank, rng):
    """Pick an item for a kart in race position `rank` (0 = leader)."""
    odds = ITEM_ODDS[min(rank, len(ITEM_ODDS) - 1)]
    total = sum(odds.values())
    r = rng.random() * total
    for item in sorted(odds):
        r -= odds[item]
        if r < 0:
            return item
    return sorted(odds)[-1]


class Box:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.respawn = 0.0

    @property
    def active(self):
        return self.respawn <= 0


class Bug:
    def __init__(self, x, y, owner):
        self.x = x
        self.y = y
        self.owner = owner
        self.life = BUG_LIFE
        self.age = 0.0


class Duck:
    def __init__(self, kart, target):
        self.x = kart.x + math.cos(kart.heading) * 6
        self.y = kart.y + math.sin(kart.heading) * 6
        self.heading = kart.heading
        self.idx = kart.idx
        self.owner = kart.id
        self.target = target   # a Kart or None
        self.life = DUCK_LIFE
        self.age = 0.0


class Items:
    def __init__(self, geo, rng):
        self.geo = geo
        self.rng = rng
        self.boxes = []
        for i in geo.box_rows:
            for lane in BOX_LANES:
                x, y = geo.place(i, lane)
                self.boxes.append(Box(x, y))
        self.bugs = []
        self.ducks = []
        self.picked = []    # box indexes picked up locally this step (for party races)

    def step(self, dt, karts, rank_of, events):
        """Advance boxes, bugs and ducks; resolve pickups and hits."""
        self.picked = []
        for bi, box in enumerate(self.boxes):
            if box.respawn > 0:
                box.respawn -= dt
                continue
            for k in karts:
                if k.fall > 0 or k.finished_ms is not None:
                    continue
                if (k.x - box.x) ** 2 + (k.y - box.y) ** 2 < BOX_RADIUS * BOX_RADIUS:
                    box.respawn = BOX_RESPAWN
                    self.picked.append(bi)
                    if not k.item:
                        k.item = roll(rank_of(k), self.rng)
                        events.append(("item", k.id, k.item))
                    break

        alive = []
        for bug in self.bugs:
            bug.life -= dt
            bug.age += dt
            hit = False
            for k in karts:
                if k.id == bug.owner and bug.age < OWNER_GRACE:
                    continue
                if (k.x - bug.x) ** 2 + (k.y - bug.y) ** 2 < BUG_RADIUS * BUG_RADIUS:
                    result = k.hit()
                    if result:
                        events.append((result, k.id, BUG))
                        hit = True
                        break
            if not hit and bug.life > 0:
                alive.append(bug)
        self.bugs = alive

        geo = self.geo
        alive = []
        for duck in self.ducks:
            duck.life -= dt
            duck.age += dt
            tgt = duck.target
            if tgt is not None and tgt.fall <= 0 and \
                    (tgt.x - duck.x) ** 2 + (tgt.y - duck.y) ** 2 < 70 * 70:
                aim_x, aim_y = tgt.x, tgt.y
            else:
                duck.idx = geo.nearest(duck.x, duck.y, duck.idx)[0]
                aim_x, aim_y = geo.place(duck.idx + 4, 0)
            want = math.atan2(aim_y - duck.y, aim_x - duck.x)
            d = want - duck.heading
            while d > math.pi:
                d -= 2 * math.pi
            while d < -math.pi:
                d += 2 * math.pi
            duck.heading += max(-6.0 * dt, min(6.0 * dt, d))
            duck.x += math.cos(duck.heading) * DUCK_SPEED * dt
            duck.y += math.sin(duck.heading) * DUCK_SPEED * dt
            hit = False
            for k in karts:
                if k.id == duck.owner and duck.age < OWNER_GRACE:
                    continue
                if (k.x - duck.x) ** 2 + (k.y - duck.y) ** 2 < DUCK_RADIUS * DUCK_RADIUS:
                    result = k.hit()
                    if result:
                        events.append((result, k.id, DUCK))
                    hit = True
                    break
            if not hit and duck.life > 0:
                alive.append(duck)
        self.ducks = alive

    def use(self, kart, karts, rank_of, events):
        """Fire the kart's item. Returns True if something was used."""
        item = kart.item
        if not item or kart.spin > 0 or kart.fall > 0:
            return False
        kart.item = 0
        if item == BOOST:
            kart.give_boost(BOOST_TIME)
        elif item == SHIELD:
            kart.shield = SHIELD_TIME
        elif item == BUG:
            bx = kart.x - math.cos(kart.heading) * 9
            by = kart.y - math.sin(kart.heading) * 9
            self.bugs.append(Bug(bx, by, kart.id))
        elif item == DUCK:
            my_rank = rank_of(kart)
            target = None
            for k in karts:
                if rank_of(k) == my_rank - 1:
                    target = k
            self.ducks.append(Duck(kart, target))
        elif item == PUSH:
            my_rank = rank_of(kart)
            for k in karts:
                if rank_of(k) < my_rank:
                    result = k.hit(1.3)
                    if result:
                        events.append((result, k.id, PUSH))
        events.append(("use", kart.id, item))
        return True

    # -- party races: things that happened on another badge ------------------------

    def remote_box(self, index):
        if 0 <= index < len(self.boxes):
            self.boxes[index].respawn = BOX_RESPAWN

    def remote_bug(self, x, y, owner):
        self.bugs.append(Bug(x, y, owner))

    def remote_duck(self, kart, target):
        self.ducks.append(Duck(kart, target))
