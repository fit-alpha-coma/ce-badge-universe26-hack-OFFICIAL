"""Logic tests for Super Mona Kart. Standard library only:

    python3 -m unittest Team2/test_super_mona_kart.py -v
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "super_mona_kart"))

import config  # noqa: E402
from config import TRACKS, CHARACTERS, BOOST, BUG, DUCK, SHIELD, PUSH, POINTS  # noqa: E402
from geom import Geometry, ROAD, CURB, DROP, SIZE  # noqa: E402
from physics import Kart, DRIFT_LEVELS  # noqa: E402
from items import Items, roll, Bug  # noqa: E402
from race import Race, Entrant, CPU, HUMAN, COUNTDOWN, RACING, award_points  # noqa: E402
from rng import Rng  # noqa: E402


def drive_to(kart, x, y):
    kart.x, kart.y = x, y


class TrackTests(unittest.TestCase):
    def test_roads_never_overlap(self):
        for spec in TRACKS:
            g = Geometry(spec)
            need = 2 * (g.road + g.curb) + 2
            self.assertGreaterEqual(g.min_clearance(), need, spec["name"])

    def test_lap_lengths_give_one_minute_races(self):
        for spec in TRACKS:
            g = Geometry(spec)
            self.assertTrue(1200 <= g.length <= 2100, (spec["name"], g.length))

    def test_everything_sits_inside_the_world_and_on_the_road(self):
        for spec in TRACKS:
            g = Geometry(spec)
            for x, y in g.points:
                margin = g.road + g.curb
                self.assertTrue(margin <= x <= SIZE - margin and margin <= y <= SIZE - margin,
                                (spec["name"], x, y))
            for slot in range(4):
                x, y, h, i = g.grid_slot(slot)
                self.assertEqual(g.surface(g.nearest(x, y, i)[2]), ROAD, spec["name"])
            for px, py, _h in g.pads:
                self.assertEqual(g.surface(g.nearest(px, py, g.nearest_global(px, py))[2]), ROAD)
            items = Items(g, Rng(1))
            for b in items.boxes:
                lat = g.nearest(b.x, b.y, g.nearest_global(b.x, b.y))[2]
                self.assertEqual(g.surface(lat), ROAD, spec["name"])

    def test_start_line_is_on_a_straight(self):
        for spec in TRACKS:
            g = Geometry(spec)
            self.assertLess(abs(g.curvature(-6, 10)), 0.6, spec["name"])


class FairnessTests(unittest.TestCase):
    def test_character_stats_sum_to_the_same_total(self):
        totals = {sum(c["stats"]) for c in CHARACTERS}
        self.assertEqual(totals, {12})

    def test_leader_never_gets_attack_or_comeback_items(self):
        rng = Rng(3)
        got = {roll(0, rng) for _ in range(2000)}
        self.assertNotIn(PUSH, got)
        self.assertNotIn(DUCK, got)

    def test_force_push_only_for_last_place(self):
        rng = Rng(4)
        for rank in (0, 1, 2):
            self.assertNotIn(PUSH, {roll(rank, rng) for _ in range(2000)})
        self.assertIn(PUSH, {roll(3, rng) for _ in range(2000)})

    def test_points_reward_winning(self):
        self.assertEqual(list(POINTS), sorted(POINTS, reverse=True))
        self.assertEqual(award_points([2, 0, 1, 3], {}), {2: 10, 0: 7, 1: 5, 3: 3})


class PhysicsTests(unittest.TestCase):
    def setUp(self):
        self.g = Geometry(TRACKS[0])

    def kart(self, char=0):
        return Kart(0, char, CHARACTERS[char]["stats"], self.g, 0)

    def test_accelerates_to_top_speed_on_the_road(self):
        k = self.kart()
        for _ in range(240):
            k.drive(1 / 60, 0, False, False)
            k.locate(0, 1 / 60)
            k.x, k.y = self.g.place(k.idx, 0)   # keep it on the centre line
            k.heading = self.g.heading_at(k.idx)
        self.assertGreater(k.forward_speed(), k.top * 0.9)

    def test_heavier_characters_have_higher_top_speed(self):
        tops = [Kart(0, i, c["stats"], self.g, 0).top for i, c in enumerate(CHARACTERS)]
        self.assertEqual(max(tops), Kart(0, 2, CHARACTERS[2]["stats"], self.g, 0).top)

    def test_drift_charges_and_releases_into_a_boost(self):
        k = self.kart()
        k.vx, k.vy = math.cos(k.heading) * 80, math.sin(k.heading) * 80
        events = []
        for _ in range(int((DRIFT_LEVELS[1] + 0.2) * 60)):
            events += k.drive(1 / 60, 1.0, False, True)
            k.vx, k.vy = math.cos(k.heading) * 80, math.sin(k.heading) * 80
        self.assertIn("drift", events)
        self.assertIn("drift2", events)
        events = k.drive(1 / 60, 1.0, False, False)
        self.assertIn("boost", events)
        self.assertGreater(k.boost, 0.8)

    def test_shield_absorbs_one_hit(self):
        k = self.kart()
        k.shield = 3.0
        self.assertEqual(k.hit(), "shield")
        self.assertEqual(k.spin, 0)
        self.assertEqual(k.hit(), "spin")
        self.assertGreater(k.spin, 0)

    def test_spinning_ignores_input(self):
        k = self.kart()
        k.vx, k.vy = math.cos(k.heading) * 60, math.sin(k.heading) * 60
        k.hit()
        before = k.forward_speed()
        k.drive(0.2, 1.0, False, True)
        self.assertEqual(k.drift, 0)
        self.assertLess(math.hypot(k.vx, k.vy), before)


class LapTests(unittest.TestCase):
    def test_laps_count_forward_and_not_backward(self):
        g = Geometry(TRACKS[0])
        k = Kart(0, 0, CHARACTERS[0]["stats"], g, 0)
        now = 0
        laps = []
        for lap in range(2):
            for i in range(g.count):
                k.x, k.y = g.place(i, 0)
                now += 50
                laps += k.locate(now, 0.05)
        self.assertEqual(k.lap, 2)
        self.assertEqual(laps.count("lap"), 2)
        # drive on a little, then backwards over the line: the lap is taken away
        for i in range(0, 10):
            k.x, k.y = g.place(i, 0)
            k.locate(now, 0.05)
        self.assertEqual(k.lap, 3)
        for i in range(10, -10, -1):
            k.x, k.y = g.place(i % g.count, 0)
            k.locate(now, 0.05)
        self.assertEqual(k.lap, 2)

    def test_cutting_across_the_infield_gains_nothing_and_respawns(self):
        g = Geometry(TRACKS[0])
        k = Kart(0, 0, CHARACTERS[0]["stats"], g, 0)
        for i in range(0, 30):
            k.x, k.y = g.place(i, 0)
            k.locate(0, 0.05)
        start = k.idx
        far = g.place(start + g.count // 2, 0)       # the other side of the lap
        k.x, k.y = (k.x + far[0]) / 2, (k.y + far[1]) / 2  # middle of the infield
        events = []
        for _ in range(70):
            events += k.locate(0, 0.05)
        moved = (k.idx - start + g.count // 2) % g.count - g.count // 2
        self.assertLessEqual(moved, 30)
        self.assertIn("respawn", events)

    def test_lava_drops_the_kart_and_puts_it_back_on_the_road(self):
        g = Geometry(TRACKS[3])
        self.assertTrue(g.drop)
        k = Kart(0, 0, CHARACTERS[0]["stats"], g, 0)
        k.x, k.y = g.place(k.idx, g.road + g.curb + 6)
        self.assertIn("fall", k.locate(0, 0.05))
        events = []
        for _ in range(100):
            events += k.drive(0.05, 0, False, False)
            if "respawn" in events:
                break
        self.assertIn("respawn", events)
        self.assertEqual(g.surface(g.nearest(k.x, k.y, k.idx)[2]), ROAD)


class ItemTests(unittest.TestCase):
    def test_bug_spins_others_but_not_its_owner_at_first(self):
        g = Geometry(TRACKS[0])
        items = Items(g, Rng(1))
        a = Kart(0, 0, CHARACTERS[0]["stats"], g, 0)
        b = Kart(1, 1, CHARACTERS[1]["stats"], g, 1)
        items.bugs.append(Bug(a.x, a.y, a.id))
        events = []
        items.step(0.01, [a], lambda k: 0, events)
        self.assertEqual(a.spin, 0)
        b.x, b.y = items.bugs[0].x, items.bugs[0].y
        items.step(0.01, [b], lambda k: 0, events)
        self.assertGreater(b.spin, 0)
        self.assertEqual(items.bugs, [])

    def test_force_push_hits_only_karts_ahead(self):
        g = Geometry(TRACKS[0])
        items = Items(g, Rng(1))
        karts = [Kart(i, i, CHARACTERS[i]["stats"], g, i) for i in range(4)]
        karts[3].item = PUSH
        ranks = {0: 0, 1: 1, 2: 2, 3: 3}
        items.use(karts[3], karts, lambda k: ranks[k.id], [])
        self.assertTrue(all(k.spin > 0 for k in karts[:3]))
        self.assertEqual(karts[3].spin, 0)


class RaceTests(unittest.TestCase):
    def test_countdown_announces_three_two_one_go(self):
        r = Race(TRACKS[0], [Entrant(0, HUMAN)], seed=1)
        seen = []
        while r.phase == COUNTDOWN:
            r.step(1 / 30, {})
            seen += [(e, n) for e, _k, n in r.events if e in ("count", "go")]
        self.assertEqual(seen, [("count", 3), ("count", 2), ("count", 1), ("go", None)])
        self.assertEqual(r.phase, RACING)

    def test_karts_cannot_move_during_the_countdown(self):
        r = Race(TRACKS[0], [Entrant(i, CPU) for i in range(4)], seed=2)
        start = [(k.x, k.y) for k in r.karts]
        for _ in range(60):
            r.step(1 / 30, {})
        self.assertEqual(start, [(k.x, k.y) for k in r.karts])

    def test_every_track_finishes_and_is_deterministic(self):
        for ti, spec in enumerate(TRACKS):
            results = []
            for _ in range(2):
                r = Race(spec, [Entrant(i, CPU) for i in range(4)], seed=99)
                while r.clock_ms < 150000 and len(r.finish_order) < 4:
                    r.step(1 / 30, {})
                results.append(r.results())
            self.assertEqual(len(r.finish_order), 4, spec["name"])
            self.assertEqual(results[0], results[1], spec["name"])

    def test_standings_put_finishers_first_in_finishing_order(self):
        r = Race(TRACKS[0], [Entrant(i, CPU) for i in range(4)], seed=5)
        r.karts[2].finished_ms = 50000
        r.karts[0].finished_ms = 51000
        r.karts[1].lap, r.karts[3].lap = 3, 2
        order = [k.id for k in r.standings()]
        self.assertEqual(order[:2], [2, 0])
        self.assertEqual(order[2:], [1, 3])


if __name__ == "__main__":
    unittest.main()
