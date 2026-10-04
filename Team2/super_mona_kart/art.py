# Images and fonts, loaded once. Uses only fonts that ship on the badge: the
# firmware's ROM pixel fonts and Mona Sans from /system/assets/fonts.

from config import CHARACTERS, TRACKS

VIEWS = 4
CELL = 32


class Art:
    def __init__(self):
        self.karts = []         # per character: [back, three-quarter, side, front]
        self.karts_half = []
        for ch in CHARACTERS:
            full = image.load("assets/kart_%s.png" % ch["key"]).spritesheet(VIEWS, 1)
            half = image.load("assets/kart_%s_half.png" % ch["key"]).spritesheet(VIEWS, 1)
            self.karts.append([full.sprite(v, 0) for v in range(VIEWS)])
            self.karts_half.append([half.sprite(v, 0) for v in range(VIEWS)])
        sheet = image.load("assets/portraits.png").spritesheet(len(CHARACTERS), 1)
        self.portraits = [sheet.sprite(i, 0) for i in range(len(CHARACTERS))]
        boxes = image.load("assets/box.png").spritesheet(4, 1)
        self.box = [boxes.sprite(i, 0) for i in range(4)]
        icons = image.load("assets/icons.png").spritesheet(5, 1)
        self.icons = [None] + [icons.sprite(i, 0) for i in range(5)]
        self.bug = image.load("assets/bug.png")
        self.duck = image.load("assets/duck.png")
        self.trophy = image.load("assets/trophy.png")
        self.title_font = None
        try:
            self.title_font = font.load("/system/assets/fonts/MonaSans-Medium.af")
        except (OSError, ValueError):
            self.title_font = None
        self.big = font.ziplock
        self.small = font.nope
        self.mid = font.sins
        self._track = None
        self._track_key = None
        self.scenery = None

    def track(self, index):
        """Texture, minimap and scenery sprites for a track (one in memory at a time)."""
        key = TRACKS[index]["key"]
        if key != self._track_key:
            self._track = None
            self.scenery = None
            import gc
            gc.collect()
            tex = image.load("assets/track_%s.png" % key)
            mini = image(64, 64)
            mini.blit(tex, rect(0, 0, 64, 64))
            sheet = image.load("assets/scenery_%s.png" % key).spritesheet(2, 1)
            self.scenery = [sheet.sprite(0, 0), sheet.sprite(1, 0)]
            self._track = (tex, mini)
            self._track_key = key
        return self._track
