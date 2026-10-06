import builtins
import importlib.util
import os
import sys
import unittest


HOST_ROOT = os.path.dirname(os.path.dirname(__file__))
APP_ROOT = os.path.dirname(HOST_ROOT)


class FakeColor:
    @staticmethod
    def rgb(*values):
        return values


class FakeShape:
    def __getattr__(self, name):
        return lambda *values: (name, values)


class FakeFont:
    nope = "nope"
    sins = "sins"
    ziplock = "ziplock"


class FakeImage:
    X2 = 2


class FakeScreen:
    width = 320
    height = 240
    clip = (0, 0, 320, 240)
    pen = None
    font = None
    antialias = None

    def clear(self):
        pass

    def text(self, *_args):
        pass

    def line(self, *_args):
        pass

    def shape(self, *_args):
        pass

    def measure_text(self, value):
        return len(str(value)) * 6, 10


class FakeBadge:
    ticks = 100
    default_clear = None

    def mode(self, _mode):
        pass

    def pressed(self, _button):
        return False

    def held(self, _button):
        return False

    def released(self, _button):
        return False

    def caselights(self, *_values):
        pass


class BadgeRenderSmokeTests(unittest.TestCase):
    def test_all_primary_screens_draw(self):
        names = {
            "badge": FakeBadge(),
            "screen": FakeScreen(),
            "image": FakeImage(),
            "font": FakeFont(),
            "color": FakeColor(),
            "shape": FakeShape(),
            "HIRES": 1,
            "VSYNC": 2,
            "BUTTON_UP": 1,
            "BUTTON_DOWN": 2,
            "BUTTON_LEFT": 3,
            "BUTTON_RIGHT": 4,
            "BUTTON_SELECT": 5,
            "BUTTON_BACK": 6,
            "BUTTON_MENU": 7,
            "BUTTON_HOME": 8,
            "run": lambda *_args, **_kwargs: None,
        }
        old_cwd = os.getcwd()
        old_path = list(sys.path)
        previous = {name: getattr(builtins, name, None) for name in names}
        missing = {name for name in names if not hasattr(builtins, name)}
        try:
            for name, value in names.items():
                setattr(builtins, name, value)
            spec = importlib.util.spec_from_file_location(
                "copilot_pager_badge_smoke", os.path.join(APP_ROOT, "__init__.py")
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            module.app.draw()
            module.app.open_request(module.sample_request())
            module.app.draw()
            module.app.decide("allow")
            self.assertEqual(module.app.result_kind, "allow")
            module.app.draw()
            for kind in ("deny", "defer", "expired", "cancelled"):
                module.app.result_kind = kind
                module.app.draw()
            module.app.state = "idle"
            module.app.draw()
            self.assertGreater(len(module.wrap_text("x" * 120)), 2)
        finally:
            os.chdir(old_cwd)
            sys.path[:] = old_path
            for name in names:
                if name in missing:
                    delattr(builtins, name)
                else:
                    setattr(builtins, name, previous[name])


if __name__ == "__main__":
    unittest.main()
