# Screens and flow: title, menus, character and track select, races, results,
# Grand Prix standings, podium, time trial and settings.

import math
from rng import Rng
from badgeware import State
from config import CHARACTERS, TRACKS, DIFFICULTY, ITEM_NAMES, POINTS
from race import Race, Entrant, HUMAN, CPU, REMOTE, COUNTDOWN, RACING, DONE, award_points, finish_unfinished
from render import World
from lights import Lights, OFF, COUNTDOWN as L_COUNT, DRIFT, FINAL, CHASE, LOBBY
from controls import Controls, menu_move, back, chord
import ui
from ui import W, H, center, text, panel, prompt, fmt_ms, ordinal

SAVE = "super_mona_kart"
DEFAULTS = {"lights": True, "assist": True, "tilt": False, "fps": False, "fast": False,
            "best": {}, "tt_best": {}, "best_lap": {}, "cups": {}, "hard": False}
MAX_SUBSTEP = 0.05      # physics never steps more than 50 ms at a time
MAX_FRAME = 0.2         # a frame slower than this is treated as 200 ms

TITLE, MENU, CHARS, DIFF, TRACKSEL, INTRO, RACE, PAUSE, RESULTS, STANDINGS, PODIUM, SETTINGS, PARTY = range(13)

MODES = (
    ("Grand Prix", "Four tracks, points, a trophy"),
    ("Quick Race", "One track, three rivals"),
    ("Time Trial", "Beat your ghost, three boosts"),
    ("Party", "Race other badges over Wi-Fi"),
    ("Settings", "Lights, steering, frame rate"),
)
GP, QUICK, TRIAL, PARTY_MODE, SETUP = range(5)


class Game:
    PARTY_STATE = PARTY

    def __init__(self, art):
        ui.init_colors()
        self.art = art
        self.save = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
        State.load(SAVE, self.save)
        for k, v in DEFAULTS.items():       # older saves may lack newer keys
            if k not in self.save:
                self.save[k] = dict(v) if isinstance(v, dict) else v
        self.lights = Lights(self.save["lights"])
        self.controls = Controls()
        self.controls.tilt = self.save["tilt"]
        self.state = TITLE
        self.state_ms = 0
        self.now = 0
        self.cursor = 0
        self.mode = GP
        self.char = 0
        self.difficulty = 1
        self.track = 0
        self.cup_race = 0
        self.totals = {}
        self.race = None
        self.world = None
        self.me = 0              # index of this badge's kart in the race
        self.banners = []
        self.ghost = None
        self.ghost_char = 0
        self.finish_ms = None
        self.fps = 0.0
        self.party = None
        self.attract = None
        self._attract_world = None
        self.rng = Rng()

    # -- helpers -----------------------------------------------------------------

    def go(self, state, cursor=0):
        self.state = state
        self.state_ms = self.now
        self.cursor = cursor

    def since(self):
        return self.now - self.state_ms

    def persist(self):
        State.save(SAVE, self.save)

    def banner(self, msg, ms=1200, pen=None):
        self.banners = [b for b in self.banners if b[1] > self.now][-2:]
        self.banners.append((msg, self.now + ms, pen))

    # -- frame -------------------------------------------------------------------

    def update(self):
        self.now = badge.ticks
        dt = min(MAX_FRAME, badge.ticks_delta / 1000)
        if badge.ticks_delta:
            self.fps += (1000.0 / badge.ticks_delta - self.fps) * 0.1
        s = self.state
        if s == TITLE:
            self.title(dt)
        elif s == MENU:
            self.menu()
        elif s == CHARS:
            self.chars()
        elif s == DIFF:
            self.diff()
        elif s == TRACKSEL:
            self.tracksel()
        elif s == INTRO:
            self.intro(dt)
        elif s == RACE:
            self.racing(dt)
        elif s == PAUSE:
            self.paused()
        elif s == RESULTS:
            self.results(dt)
        elif s == STANDINGS:
            self.standings()
        elif s == PODIUM:
            self.podium(dt)
        elif s == SETTINGS:
            self.settings()
        elif s == PARTY:
            self.party_screen(dt)
        self.lights.update(self.now)

    def exit(self):
        self.lights.off()
        if self.party:
            self.party.close()

    # -- title and menus -----------------------------------------------------------

    def new_attract(self):
        """A computer-only race that plays behind the title and the menus."""
        t = self.rng.randrange(len(TRACKS))
        self.attract = Race(TRACKS[t], [Entrant(i, CPU) for i in range(4)], difficulty=1,
                            seed=self.rng.randrange(1 << 20))
        self.attract.clock_ms = 0
        self.attract.phase = RACING
        self._attract_world = World(self.art, t, TRACKS[t])
        self._attract_world.follow(*self._lead_pose(), 0, snap=True)

    def title(self, dt):
        if self.attract is None or self.attract.phase == DONE or len(self.attract.finish_order) >= 2:
            self.new_attract()
        r = self.attract
        r.step(dt, {})
        w = self._attract_world
        w.follow(*self._lead_pose(), dt)
        w.draw_background()
        w.draw_sprites(r.karts, r.items, self.now)
        self.lights.set(OFF)
        panel(30, 52, W - 60, 112)
        a = self.art
        if a.title_font:
            center("SUPER MONA KART", 62, a.title_font, ui.GOLD, size=26)
        else:
            center("SUPER MONA KART", 64, a.big, ui.GOLD, size=2)
        center("The badge mascots' Grand Prix", 98, a.small, ui.WHITE)
        for i in range(4):
            p = a.portraits[i]
            screen.blit(p, rect(70 + i * 46, 116, 32, 32))
        if (self.now // 500) % 2:
            prompt([("SEL", "start")], 176, a.small)
        if badge.pressed(BUTTON_SELECT):
            self.go(MENU, self.mode)

    def _lead_pose(self):
        lead = self.attract.standings()[0]
        return lead.x, lead.y, lead.heading

    def backdrop(self):
        """Menus reuse the attract race behind a dark veil."""
        if self.attract is None or len(self.attract.finish_order) >= 2:
            self.new_attract()
        if self.attract is not None:
            w = self._attract_world
            self.attract.step(1 / 30, {})
            w.follow(*self._lead_pose(), 1 / 30)
            w.draw_background()
            w.draw_sprites(self.attract.karts, self.attract.items, self.now)
        screen.pen = color.rgb(8, 10, 26, 170)
        screen.rectangle(0, 0, W, H)

    def menu(self):
        self.backdrop()
        a = self.art
        ui.heading("SUPER MONA KART", 10, a, 22)
        for i, (name, desc) in enumerate(MODES):
            y = 46 + i * 34
            sel = i == self.cursor
            panel(46, y, W - 92, 31, color.rgb(60, 90, 200, 210) if sel else None)
            ui.label(name, 58, y + 2, a, 14, ui.WHITE if sel else ui.DIM)
            text(desc, 58, y + 18, a.small, ui.ACCENT if sel else ui.DIM, shadow=False)
        prompt([("^v", "move"), ("SEL", "choose"), ("BK/<", "back")], H - 18, a.small)
        self.cursor = (self.cursor + menu_move()) % len(MODES)
        if back(BUTTON_LEFT):
            self.go(TITLE)
        elif badge.pressed(BUTTON_SELECT):
            self.mode = self.cursor
            if self.mode == SETUP:
                self.go(SETTINGS)
            elif self.mode == PARTY_MODE:
                from party import Party
                self.party = Party(self)
                self.go(PARTY)
            else:
                self.go(CHARS, self.char)

    def chars(self):
        self.backdrop()
        a = self.art
        ui.heading("Choose your racer", 6, a, 20, ui.WHITE)
        n = len(CHARACTERS)
        for i in range(n):
            x = 40 + i * 64
            sel = i == self.cursor
            panel(x, 38, 48, 48, color.rgb(60, 90, 200, 220) if sel else None)
            screen.blit(a.portraits[i], rect(x + 8, 46, 32, 32))
        ch = CHARACTERS[self.cursor]
        panel(16, 94, W - 32, 122)
        view = (self.now // 700) % 4
        screen.blit(a.karts[self.cursor][view], rect(24, 110, 96, 96))
        ui.label(ch["name"], 132, 98, a, 20, ui.GOLD)
        text("from " + ch["app"], 132, 124, a.small, ui.DIM, shadow=False)
        text(ch["blurb"], 132, 136, a.small, ui.ACCENT, shadow=False)
        ui.stat_bars(ch["stats"], 132, 154, a.small)
        prompt([("<>", "pick"), ("SEL", "race"), ("BK/^", "back")], H - 18, a.small)
        if badge.pressed(BUTTON_LEFT):
            self.cursor = (self.cursor - 1) % n
        elif badge.pressed(BUTTON_RIGHT):
            self.cursor = (self.cursor + 1) % n
        if back(BUTTON_UP):
            self.go(MENU, self.mode)
        elif badge.pressed(BUTTON_SELECT):
            self.char = self.cursor
            if self.mode == GP:
                self.go(DIFF, self.difficulty)
            else:
                self.go(TRACKSEL, self.track)

    def diff(self):
        self.backdrop()
        a = self.art
        ui.heading("Octo Cup", 8, a, 22)
        center("Four tracks. Points: " + " / ".join(str(p) for p in POINTS), 42, a.small, ui.DIM)
        for i, d in enumerate(DIFFICULTY):
            y = 70 + i * 40
            locked = i == 2 and not self.save["hard"]
            sel = i == self.cursor
            panel(70, y, W - 140, 32, color.rgb(60, 90, 200, 210) if sel else None)
            name = d["name"] + ("  (win Normal to unlock)" if locked else "")
            ui.label(name, 82, y + 3, a, 14, ui.DIM if locked else ui.WHITE)
            cup = self.save["cups"].get(str(i))
            if cup:
                text(("Gold", "Silver", "Bronze", "")[min(cup, 4) - 1], 82, y + 18, a.small, ui.GOLD, shadow=False)
        prompt([("^v", "move"), ("SEL", "start"), ("BK/<", "back")], H - 18, a.small)
        self.cursor = (self.cursor + menu_move()) % len(DIFFICULTY)
        if back(BUTTON_LEFT):
            self.go(CHARS, self.char)
        elif badge.pressed(BUTTON_SELECT) and not (self.cursor == 2 and not self.save["hard"]):
            self.difficulty = self.cursor
            self.cup_race = 0
            self.totals = {}
            self.start_race(0)

    def tracksel(self):
        self.backdrop()
        a = self.art
        ui.heading("Choose a track", 6, a, 20, ui.WHITE)
        for i, tr in enumerate(TRACKS):
            x = 14 + (i % 2) * 150
            y = 40 + (i // 2) * 86
            sel = i == self.cursor
            panel(x, y, 142, 80, color.rgb(60, 90, 200, 220) if sel else None)
            text(tr["name"], x + 6, y + 4, a.small, ui.WHITE if sel else ui.DIM)
            best = self.save["tt_best" if self.mode == TRIAL else "best"].get(tr["key"])
            text("Best " + fmt_ms(best), x + 6, y + 64, a.small, ui.GOLD if best else ui.DIM, shadow=False)
            screen.pen = color.rgb(*tr["ground"][0])
            screen.shape(shape.rounded_rectangle(x + 90, y + 16, 46, 46, 4))
            pts = tr["layout"]
            screen.pen = color.rgb(*tr["road_rgb"])
            for j in range(len(pts)):
                ax, ay = pts[j]
                bx, by = pts[(j + 1) % len(pts)]
                screen.shape(shape.line(x + 90 + ax * 46 / 256, y + 16 + ay * 46 / 256,
                                        x + 90 + bx * 46 / 256, y + 16 + by * 46 / 256, 3))
        prompt([("<>", "pick"), ("SEL", "race"), ("BK/^", "back")], H - 18, a.small)
        m = 0
        if badge.pressed(BUTTON_LEFT):
            m = -1
        elif badge.pressed(BUTTON_RIGHT) or badge.pressed(BUTTON_DOWN):
            m = 1
        self.cursor = (self.cursor + m) % len(TRACKS)
        if back(BUTTON_UP):
            self.go(CHARS, self.char)
        elif badge.pressed(BUTTON_SELECT):
            self.track = self.cursor
            self.start_race(self.track)

    # -- racing ------------------------------------------------------------------

    def start_race(self, track):
        self.track = track
        self.me = 0
        spec = TRACKS[track]
        self.attract = None
        self._attract_world = None
        import gc
        gc.collect()
        if self.mode == TRIAL:
            ents = [Entrant(self.char, HUMAN)]
            self.race = Race(spec, ents, items=False, start_boosts=3, seed=1, grid=[0], record_ghost=True)
            g = self._load_ghost(spec["key"])
            self.ghost, self.ghost_char = g if g else (None, 0)
        else:
            others = [i for i in range(len(CHARACTERS)) if i != self.char]
            ents = [Entrant(self.char, HUMAN)] + [Entrant(i, CPU) for i in others]
            if self.mode == GP and self.cup_race > 0:
                # grid by points: the leader starts on pole
                order = sorted(range(4), key=lambda i: -self.totals.get(i, 0))
                grid = [0] * 4
                for slot, idx in enumerate(order):
                    grid[idx] = slot
            else:
                grid = [3, 0, 1, 2]   # the player starts at the back
            diff = self.difficulty if self.mode == GP else 1
            self.race = Race(spec, ents, difficulty=diff, seed=self.rng.randrange(1 << 20), grid=grid)
            self.ghost = None
        self._enter_race(track)

    def start_party_race(self, track):
        """The party module has built self.race and set self.me."""
        self.mode = PARTY_MODE
        self.track = track
        self.ghost = None
        self.attract = None
        self._attract_world = None
        self._enter_race(track)

    def _enter_race(self, track):
        import gc
        gc.collect()
        self.world = World(self.art, track, TRACKS[track], fast=self.save["fast"])
        k = self.race.karts[self.me]
        self.world.follow(k.x, k.y, k.heading, 0, snap=True)
        self.banners = []
        self.finish_ms = None
        self.go(INTRO)

    def intro(self, dt):
        w = self.world
        k = self.race.karts[self.me]
        t = self.since() / 2200.0
        # swing the camera in from the side onto the grid
        ang = k.heading + (1.0 - min(1.0, t)) * 2.2
        w.follow(k.x, k.y, ang, dt, snap=True)
        w.draw_background()
        w.draw_sprites(self.race.karts, self.race.items, self.now, highlight=k)
        a = self.art
        spec = TRACKS[self.track]
        panel(20, 26, W - 40, 66)
        ui.heading(spec["name"], 32, a, 22)
        sub = {GP: "Race %d of %d" % (self.cup_race + 1, len(TRACKS)),
               QUICK: "Quick Race", TRIAL: "Time Trial", PARTY_MODE: "Party race"}.get(self.mode, "")
        center(sub + "  -  %d laps" % self.race.laps, 70, a.small, ui.WHITE)
        prompt([("<>", "steer"), ("SEL", "item"), ("BK/^", "drift"), ("v", "brake")], H - 34, a.small)
        prompt([("MN/^v", "pause")] if not self.party else [], H - 18, a.small)
        if self.party:
            self.party.before_step(0)    # keep receiving while the card shows
            if self.party.started_countdown():
                self.go(RACE)
        elif self.since() > 2400 or badge.pressed(BUTTON_SELECT):
            self.go(RACE)

    def racing(self, dt):
        r = self.race
        me = r.karts[self.me]
        a = self.art
        controls = {self.me: self.controls.race(min(dt, MAX_SUBSTEP), self.save["assist"])}
        if self.party:
            self.party.before_step(dt)
        # slow frames run several short physics steps, so a badge at 15 fps
        # drives exactly as far as one at 60 fps
        n = 1
        while dt / n > MAX_SUBSTEP:
            n += 1
        sub = dt / n
        for i in range(n):
            clock = self.party.clock() if (self.party and i == n - 1) else None
            r.step(sub, controls, clock)
            self.handle_events(r.events, me)
            if i == 0:
                controls = {self.me: controls[self.me][:3] + (False,) + controls[self.me][4:]}
        if self.party:
            self.party.after_step(dt)
        w = self.world
        w.follow(me.x, me.y, me.heading, dt)
        if w.shake > 0:
            w.shake -= dt
        w.draw_background()
        ghost = self._ghost_pose() if self.ghost else None
        w.draw_sprites(r.karts, r.items, self.now, ghost=ghost, highlight=me)
        ui.hud(r, me, a, w, self.now, r.laps, self.save["fps"], self.fps)
        if r.phase == COUNTDOWN:
            n = (-r.clock_ms + 999) // 1000
            msg = str(n)
            f = a.title_font or a.big
            size = 64 if a.title_font else 4
            center(msg, 70, f, ui.GOLD, size=size)
            self.lights.set(L_COUNT, n)
        elif r.clock_ms < 800:
            f = a.title_font or a.big
            center("GO!", 70, f, color.rgb(120, 255, 140), size=64 if a.title_font else 4)
        for msg, until, pen in self.banners:
            if until > self.now:
                ui.heading(msg, 56, a, 16, pen or ui.WHITE)
                break
        if me.finished_ms is not None:
            if self.finish_ms is None:
                self.finish_ms = self.now
            place = r.finish_order.index(me.id) + 1
            f = a.title_font or a.big
            center("FINISH!", 72, f, ui.GOLD, size=36 if a.title_font else 3)
            center(ordinal(place) + " place", 116, a.big, ui.WHITE, size=2)
            waited = self.now - self.finish_ms
            everyone = len(r.finish_order) == len(r.karts)
            patience = 12000 if self.party else 7000
            if waited > 2500 and (everyone or waited > patience or self.mode == TRIAL):
                finish_unfinished(r)
                self.end_race()
        elif (badge.pressed(BUTTON_MENU) or chord()) and not self.party:
            self.go(PAUSE)
        if r.phase == RACING and me.finished_ms is None:
            if me.drift:
                self.lights.set(DRIFT, me.level)
            elif me.lap == r.laps:
                self.lights.set(FINAL)
            else:
                self.lights.set(OFF)

    def handle_events(self, events, me):
        for name, kid, extra in events:
            mine = kid == me.id
            if name == "go":
                self.lights.flash("go", self.now, 500)
                self.lights.set(OFF)
            elif mine and name in ("boost", "pad"):
                self.lights.flash("boost", self.now, 350)
            elif mine and name == "item":
                self.lights.flash("item", self.now, 250)
                self.banner(ITEM_NAMES[extra] + "!", 900, ui.ACCENT)
            elif mine and name == "spin":
                self.lights.flash("hit", self.now, 540)
                self.world.shake = 0.35
            elif mine and name == "shield":
                self.banner("Copilot Shield saved you!", 1000, ui.ACCENT)
            elif mine and name == "fall":
                self.banner("Into the lava!", 1100, color.rgb(255, 140, 60))
            elif mine and name == "lap" and me.finished_ms is None and 1 < me.lap <= self.race.laps:
                if me.lap == self.race.laps:
                    self.banner("FINAL LAP!", 1500, ui.GOLD)
                else:
                    self.banner("LAP %d" % me.lap, 1000)
            elif name == "finish" and mine:
                self.lights.set(CHASE if extra == 1 else OFF)
            elif name == "use" and not mine and extra == 5:
                self.banner("Force Push!", 900, color.rgb(255, 120, 140))

    def _ghost_pose(self):
        t = self.race.clock_ms / 100.0
        if t < 0:
            t = 0
        g = self.ghost
        i = int(t)
        if i >= len(g) - 1:
            x, y, h = g[-1]
            return (x, y, h, self.ghost_char)
        f = t - i
        x0, y0, h0 = g[i]
        x1, y1, h1 = g[i + 1]
        return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, h0, self.ghost_char)

    def _load_ghost(self, key):
        data = {"g": None, "c": 0}
        State.load("smk_ghost_" + key, data)
        if data["g"]:
            return data["g"], data["c"]
        return None

    def end_race(self):
        r = self.race
        me = r.karts[self.me]
        key = TRACKS[self.track]["key"]
        if me.finished_ms is not None and not me.dnf:
            # time trials (no items, three boosts) keep their own records and ghost
            table = "tt_best" if self.mode == TRIAL else "best"
            best = self.save[table].get(key)
            self.new_record = best is None or me.finished_ms < best
            if self.new_record:
                self.save[table][key] = me.finished_ms
                if self.mode == TRIAL:
                    State.save("smk_ghost_" + key, {"g": r.ghost, "c": self.char})
            lap = self.save["best_lap"].get(key)
            if me.best_lap_ms and (lap is None or me.best_lap_ms < lap):
                self.save["best_lap"][key] = me.best_lap_ms
            self.persist()
        else:
            self.new_record = False
        if self.mode == GP:
            award_points(r.finish_order, self.totals)
        self.go(RESULTS)

    def paused(self):
        w = self.world
        w.draw_background()
        w.draw_sprites(self.race.karts, self.race.items, self.now, highlight=self.race.karts[self.me])
        a = self.art
        panel(60, 60, W - 120, 110)
        ui.heading("Paused", 66, a, 22)
        opts = ("Resume", "Restart race", "Quit to menu")
        for i, o in enumerate(opts):
            sel = i == self.cursor
            center(("> " if sel else "") + o, 102 + i * 20, a.small, ui.WHITE if sel else ui.DIM)
        self.cursor = (self.cursor + menu_move()) % len(opts)
        self.lights.set(OFF)
        if badge.pressed(BUTTON_MENU) or back(BUTTON_LEFT) or chord():
            self.cursor = 0
            self.state = RACE
        elif badge.pressed(BUTTON_SELECT):
            if self.cursor == 0:
                self.state = RACE
            elif self.cursor == 1:
                self.start_race(self.track)
            else:
                self.go(MENU, self.mode)

    def results(self, dt):
        r = self.race
        if self.party:
            self.party.before_step(dt)
        r.step(dt, {})
        if self.party:
            self.party.after_step(dt)
        w = self.world
        me = r.karts[self.me]
        w.follow(me.x, me.y, me.heading, dt)
        w.draw_background()
        w.draw_sprites(r.karts, r.items, self.now)
        a = self.art
        panel(24, 20, W - 48, 196)
        title = TRACKS[self.track]["name"]
        ui.heading(title, 24, a, 16)
        if self.mode == TRIAL:
            center(fmt_ms(me.finished_ms), 56, a.big, ui.WHITE, size=2)
            if self.new_record:
                center("NEW RECORD - your ghost is saved", 92, a.small, ui.GOLD)
            center("Best lap " + fmt_ms(me.best_lap_ms), 112, a.small, ui.WHITE)
        else:
            for place, kid in enumerate(r.finish_order):
                k = r.karts[kid]
                y = 50 + place * 28
                pen = ui.GOLD if kid == me.id else ui.WHITE
                text(ordinal(place + 1), 36, y + 4, a.small, pen)
                screen.blit(a.portraits[k.char], rect(70, y - 2, 24, 24))
                name = CHARACTERS[k.char]["name"]
                if self.party and kid == me.id:
                    name += " (you)"
                elif self.party and r.entrants[kid].kind == REMOTE and kid in self.party.kart_of.values():
                    name += " (badge)"
                text(name, 100, y + 4, a.small, pen)
                text(fmt_ms(k.finished_ms) if k.finished_ms else "--", 170, y + 4, a.small, pen)
                if self.mode == GP and place < len(POINTS):
                    text("+%d" % POINTS[place], 250, y + 4, a.small, ui.ACCENT)
            if self.new_record:
                center("New track record!", 168, a.small, ui.GOLD)
        prompt([("SEL", "continue")], 196, a.small)
        if self.since() > 800 and badge.pressed(BUTTON_SELECT):
            self.lights.set(OFF)
            if self.mode == GP:
                self.go(STANDINGS)
            elif self.mode == PARTY_MODE and self.party:
                self.party.back_to_lobby()
                self.go(PARTY)
            elif self.mode == TRIAL:
                self.go(TRACKSEL, self.track)
            else:
                self.go(MENU, self.mode)

    def standings(self):
        self.world.draw_background()
        a = self.art
        panel(24, 20, W - 48, 196)
        last = self.cup_race == len(TRACKS) - 1
        ui.heading("Cup standings" + (" - final" if last else ""), 24, a, 16)
        order = sorted(range(4), key=lambda i: -self.totals.get(i, 0))
        for place, idx in enumerate(order):
            ch = self.race.entrants[idx].char
            y = 52 + place * 30
            pen = ui.GOLD if idx == 0 else ui.WHITE
            text(ordinal(place + 1), 40, y + 4, a.small, pen)
            screen.blit(self.art.portraits[ch], rect(74, y - 2, 24, 24))
            text(CHARACTERS[ch]["name"], 104, y + 4, a.small, pen)
            text("%d pts" % self.totals.get(idx, 0), 220, y + 4, a.small, pen)
        nxt = "podium" if last else "next: " + TRACKS[self.cup_race + 1]["name"]
        prompt([("SEL", nxt)], 196, a.small)
        if self.since() > 600 and badge.pressed(BUTTON_SELECT):
            if last:
                self.go(PODIUM)
                self.award_cup(order)
            else:
                self.cup_race += 1
                self.start_race(self.cup_race)

    def award_cup(self, order):
        place = order.index(0) + 1
        key = str(self.difficulty)
        prev = self.save["cups"].get(key)
        if place <= 3 and (prev is None or place < prev):
            self.save["cups"][key] = place
        if self.difficulty == 1 and place == 1:
            self.save["hard"] = True
        self.persist()
        self.cup_place = place

    def podium(self, dt):
        a = self.art
        screen.pen = color.rgb(20, 24, 60)
        screen.rectangle(0, 0, W, H)
        order = sorted(range(4), key=lambda i: -self.totals.get(i, 0))
        steps = ((1, 120, 140), (0, 150, 120), (2, 90, 156))   # (place, x... )
        heights = {0: 70, 1: 50, 2: 36}
        xs = {0: 136, 1: 76, 2: 196}
        for place in (1, 0, 2):
            idx = order[place]
            ch = self.race.entrants[idx].char
            x = xs[place]
            h = heights[place]
            screen.pen = color.rgb(*((255, 208, 64), (200, 206, 220), (205, 127, 50))[place])
            screen.shape(shape.rounded_rectangle(x, 200 - h, 48, h + 40, 4))
            text(str(place + 1), x + 20, 206 - h, a.big, color.rgb(30, 30, 50), shadow=False)
            bob = int(math.sin(self.now / 200.0 + place) * 3)
            screen.blit(a.karts[ch][3], rect(x - 8, 136 - h + bob, 64, 64))
        rng = Rng(self.now // 120)
        for _ in range(28):
            screen.pen = color.rgb(rng.randrange(256), rng.randrange(256), rng.randrange(256))
            screen.rectangle(rng.randrange(W), (rng.randrange(H) + self.now // 8) % H, 3, 3)
        place = self.cup_place
        msg = {1: "You won the Octo Cup!", 2: "Silver trophy!", 3: "Bronze trophy!"}.get(place, "Better luck next cup")
        ui.heading(msg, 8, a, 22)
        if place <= 3:
            screen.blit(a.trophy, rect(W // 2 - 24, 40, 48, 48))
        self.lights.set(CHASE if place == 1 else OFF)
        prompt([("SEL", "menu")], H - 18, a.small)
        if self.since() > 1500 and badge.pressed(BUTTON_SELECT):
            self.lights.set(OFF)
            self.go(MENU, self.mode)

    # -- settings ------------------------------------------------------------------

    def settings(self):
        self.backdrop()
        a = self.art
        ui.heading("Settings", 10, a, 22)
        rows = (("Case lights", "lights"), ("Steering assist", "assist"),
                ("Tilt steering", "tilt"), ("Fast graphics", "fast"), ("Show frame rate", "fps"))
        for i, (name, key) in enumerate(rows):
            y = 46 + i * 28
            sel = i == self.cursor
            panel(50, y, W - 100, 25, color.rgb(60, 90, 200, 210) if sel else None)
            ui.label(name, 62, y + 4, a, 14, ui.WHITE if sel else ui.DIM)
            ui.label("On" if self.save[key] else "Off", W - 92, y + 4, a, 14, ui.ACCENT if self.save[key] else ui.DIM)
        y = 46 + len(rows) * 28
        sel = self.cursor == len(rows)
        panel(50, y, W - 100, 25, color.rgb(160, 60, 60, 210) if sel else None)
        ui.label("Clear records", 62, y + 4, a, 14, ui.WHITE if sel else ui.DIM)
        prompt([("^v", "move"), ("SEL", "change"), ("BK/<", "back")], H - 18, a.small)
        self.cursor = (self.cursor + menu_move()) % (len(rows) + 1)
        if back(BUTTON_LEFT):
            self.persist()
            self.go(MENU, SETUP)
        elif badge.pressed(BUTTON_SELECT):
            if self.cursor < len(rows):
                key = rows[self.cursor][1]
                self.save[key] = not self.save[key]
                self.lights.enabled = self.save["lights"]
                self.controls.tilt = self.save["tilt"]
                if key == "tilt" and self.save["tilt"]:
                    self.controls.calibrate()
                if key == "lights" and self.save["lights"]:
                    self.lights.flash("boost", self.now, 400)
            else:
                for k in ("best", "tt_best", "best_lap", "cups"):
                    self.save[k] = {}
                self.save["hard"] = False
                for tr in TRACKS:
                    State.delete("smk_ghost_" + tr["key"])
                self.banner("Records cleared", 900)
            self.persist()

    def party_screen(self, dt):
        if self.party.update(dt) == "menu":
            self.party.close()
            self.party = None
            self.go(MENU, PARTY_MODE)
