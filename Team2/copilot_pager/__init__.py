"""Copilot Pager: review Copilot permission requests on a Universe badge."""

import json
import math
import os
import sys


try:
    APP_DIR = __file__.rsplit("/", 1)[0] if "/" in __file__ else "/system/apps/copilot_pager"
except NameError:
    # Code pasted into the web simulator executes without a __file__ value.
    APP_DIR = "/"
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

from ble_transport import PagerTransport


badge.mode(HIRES | VSYNC)
screen.antialias = image.X2

# The upstream Tufty web simulator predates the Universe 2026 logical control
# names plus its Menu and Back controls. Keep the physical badge mapping, but
# make its A/B/C model useful for UI previews: B opens the safe demo and A
# doubles as Back.
SIMULATOR_CONTROLS = False
try:
    BUTTON_LEFT
    BUTTON_SELECT
    BUTTON_RIGHT
except NameError:
    BUTTON_LEFT = BUTTON_A
    BUTTON_SELECT = BUTTON_B
    BUTTON_RIGHT = BUTTON_C
    SIMULATOR_CONTROLS = True

try:
    BUTTON_MENU
    BUTTON_BACK
except NameError:
    BUTTON_MENU = BUTTON_SELECT
    BUTTON_BACK = BUTTON_LEFT
    SIMULATOR_CONTROLS = True

BG = color.rgb(13, 17, 23)
PANEL = color.rgb(22, 27, 34)
PANEL_2 = color.rgb(33, 38, 45)
BORDER = color.rgb(48, 54, 61)
TEXT = color.rgb(240, 246, 252)
MUTED = color.rgb(139, 148, 158)
BLUE = color.rgb(88, 166, 255)
PURPLE = color.rgb(163, 113, 247)
GREEN = color.rgb(63, 185, 80)
RED = color.rgb(248, 81, 73)
ORANGE = color.rgb(210, 153, 34)

TITLE_FONT = font.nope
BODY_FONT = font.sins
CODE_FONT = font.ziplock

WIDTH = screen.width
HEIGHT = screen.height
HEADER_H = 36
FOOTER_H = 31
CONTENT_TOP = HEADER_H + 37
CONTENT_BOTTOM = HEIGHT - FOOTER_H - 4
LINE_H = 14
WRAP_COLUMNS = 49


def clamp(value, low, high):
    return max(low, min(high, value))


def shorten(value, limit):
    value = str(value or "")
    return value if len(value) <= limit else value[: max(0, limit - 3)] + "..."


def wrap_text(value, columns=WRAP_COLUMNS):
    """Small deterministic wrapper that also handles commands without spaces."""
    text = str(value or "")
    lines = []
    for source_line in text.replace("\t", "  ").splitlines() or [""]:
        prefix = ""
        if source_line.startswith(("+", "-")):
            prefix = source_line[0]
        remaining = source_line
        while len(remaining) > columns:
            split = remaining.rfind(" ", 0, columns + 1)
            if split < columns // 2:
                split = columns
            lines.append((prefix if lines and prefix else "") + remaining[:split].rstrip())
            remaining = remaining[split:].lstrip()
        lines.append((prefix if prefix and not remaining.startswith(prefix) else "") + remaining)
    return lines or [""]


def json_pretty(value):
    try:
        return json.dumps(value, indent=2, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def request_sections(request):
    sections = []
    summary = request.get("summary") or "%s permission request" % request.get("tool_name", "Tool")
    sections.append(("SUMMARY", wrap_text(summary)))
    command = request.get("command")
    if command:
        sections.append(("COMMAND", wrap_text(command)))
    diff = request.get("diff")
    if diff:
        sections.append(("CHANGES", wrap_text(diff)))
    arguments = request.get("arguments")
    if arguments not in (None, "", {}):
        value = arguments if isinstance(arguments, str) else json_pretty(arguments)
        sections.append(("ARGUMENTS", wrap_text(value)))
    context = request.get("context")
    if context:
        sections.append(("CONTEXT", wrap_text(context)))
    blocked_reason = request.get("blocked_reason")
    if blocked_reason:
        sections.append(("LAPTOP REQUIRED", wrap_text(blocked_reason)))
    if request.get("truncated"):
        sections.append(
            (
                "LIMIT",
                wrap_text("Payload was too large for safe remote approval. Review it on the laptop."),
            )
        )
    return sections


def sample_request():
    value = {
        "v": 1,
        "id": "demo-request",
        "payload_digest": "demo",
        "source": "DEMO",
        "repo": "octocat/hello-world",
        "tool_name": "bash",
        "permission_kind": "commands",
        "summary": "Copilot wants to run the project test suite",
        "command": "npm test -- --runInBand",
        "arguments": {"cwd": "/workspace/hello-world"},
        "context": "This is a safe, simulated request. No command will run.",
        "allow_remote": True,
        "timeout_ms": 90000,
        "demo": True,
    }
    return value


class PagerApp:
    def __init__(self):
        self.transport = PagerTransport()
        self.request = None
        self.sections = []
        self.section = 0
        self.scroll = 0
        self.deadline = 0
        self.state = "setup" if self.transport.pairing is None else "idle"
        self.result = ""
        self.result_kind = "defer"
        self.result_demo = False
        self.result_until = 0
        self.select_started = None
        self.right_started = None
        self.hold_action_done = False
        self.last_light = None
        self.last_repo = "Waiting for Copilot"
        self.connection_note = ""
        self.last_decision = None

    def open_request(self, request):
        if self.request is not None and request.get("id") == self.request.get("id"):
            self.connection_note = "Reconnected - request restored"
            return
        if self.last_decision is not None:
            previous, decision, valid_until = self.last_decision
            same = (
                previous.get("id") == request.get("id")
                and previous.get("payload_digest") == request.get("payload_digest")
            )
            if same and badge.ticks < valid_until:
                if self.transport.send_decision(request, decision):
                    self.finish("decision resent", decision)
                return
        self.request = request
        self.sections = request_sections(request)
        self.section = 0
        self.scroll = 0
        self.deadline = badge.ticks + clamp(int(request.get("timeout_ms", 90000)), 1000, 90000)
        self.last_repo = request.get("repo") or self.last_repo
        self.state = "request"
        self.result = ""
        self.select_started = None
        self.right_started = None
        self.hold_action_done = False

    def handle_transport(self):
        for kind, value in self.transport.poll():
            if kind == "request":
                self.open_request(value)
            elif kind == "cancel" and self.request is not None:
                if not value.get("id") or value.get("id") == self.request.get("id"):
                    self.finish("cancelled", "cancelled")
            elif kind == "connection":
                self.connection_note = "Connected" if value else "Connection lost - waiting"
            elif kind == "error":
                self.connection_note = str(value)

    def finish(self, result, kind="defer"):
        self.result = result
        self.result_kind = kind
        self.result_demo = bool(self.request and self.request.get("demo"))
        self.state = "result"
        self.result_until = badge.ticks + 2200
        self.request = None
        self.sections = []
        self.select_started = None
        self.right_started = None

    def decide(self, decision, result=None):
        if self.request is None:
            return
        if decision == "allow" and not self.request.get("allow_remote", True):
            decision = "defer"
        label = result or {
            "allow": "approved",
            "deny": "denied",
            "defer": "sent to laptop",
        }[decision]
        result_kind = "expired" if result == "expired" else decision
        if self.request.get("demo"):
            self.finish("demo " + label, result_kind)
            return
        if self.transport.send_decision(self.request, decision):
            self.last_decision = (dict(self.request), decision, badge.ticks + 120000)
            self.finish(label, result_kind)
        else:
            self.connection_note = "Could not send - reconnecting"

    def update_holds(self):
        if self.state != "request":
            return
        now = badge.ticks
        if badge.pressed(BUTTON_SELECT):
            self.select_started = now
            self.hold_action_done = False
        if self.select_started is not None and badge.held(BUTTON_SELECT):
            if not self.hold_action_done and now - self.select_started >= 1000:
                self.hold_action_done = True
                self.decide("allow")
                return
        if badge.released(BUTTON_SELECT):
            self.select_started = None

        if badge.pressed(BUTTON_RIGHT):
            self.right_started = now
            self.hold_action_done = False
        if self.right_started is not None and badge.held(BUTTON_RIGHT):
            if not self.hold_action_done and now - self.right_started >= 1000:
                self.hold_action_done = True
                self.decide("defer")
                return
        if badge.released(BUTTON_RIGHT):
            duration = now - self.right_started if self.right_started is not None else 0
            if not self.hold_action_done and duration < 1000 and self.sections:
                self.section = (self.section + 1) % len(self.sections)
                self.scroll = 0
            self.right_started = None

    def handle_input(self):
        if self.state in ("setup", "idle") and badge.pressed(BUTTON_MENU):
            self.open_request(sample_request())
            return
        if self.state != "request":
            return
        if badge.pressed(BUTTON_LEFT) or badge.pressed(BUTTON_BACK):
            self.decide("deny")
            return
        if badge.pressed(BUTTON_UP):
            self.scroll = max(0, self.scroll - 1)
        if badge.pressed(BUTTON_DOWN):
            lines = self.sections[self.section][1] if self.sections else []
            visible = max(1, (CONTENT_BOTTOM - CONTENT_TOP) // LINE_H)
            self.scroll = min(max(0, len(lines) - visible), self.scroll + 1)
        self.update_holds()

    def tick(self):
        self.handle_transport()
        self.handle_input()
        if self.state == "request" and badge.ticks >= self.deadline:
            self.decide("defer", "expired")
        if self.state == "result" and badge.ticks >= self.result_until:
            self.state = "idle" if self.transport.pairing else "setup"
        self.update_lights()

    def update_lights(self):
        values = (0.0, 0.0, 0.0, 0.0)
        if self.state == "request":
            pulse = 0.12 + 0.18 * (1.0 + math.sin(badge.ticks / 180.0))
            active = (badge.ticks // 220) % 4
            values = tuple(pulse if index == active else 0.04 for index in range(4))
        elif self.state == "result":
            on = badge.ticks % 300 < 170
            level = 0.8 if on else 0.0
            values = (level, level, level, level)
        quantized = tuple(int(value * 50) for value in values)
        if quantized != self.last_light:
            self.last_light = quantized
            try:
                badge.caselights(*values)
            except (AttributeError, ValueError):
                pass

    def draw_header(self, title="COPILOT PAGER"):
        screen.pen = BG
        screen.clear()
        screen.font = TITLE_FONT
        screen.pen = TEXT
        screen.text(title, 12, 9)
        status_pen = GREEN if self.transport.connected else MUTED
        screen.pen = status_pen
        screen.shape(shape.circle(WIDTH - 17, 17, 5))
        screen.pen = BORDER
        screen.line(10, HEADER_H - 1, WIDTH - 10, HEADER_H - 1)

    def draw_idle(self):
        self.draw_header()
        center_x = WIDTH // 2
        center_y = 111
        phase = (badge.ticks % 1800) / 1800.0
        for index in range(3):
            radius = 27 + ((phase + index / 3.0) % 1.0) * 44
            screen.pen = color.rgb(33 + index * 6, 58 + index * 9, 82 + index * 14)
            screen.shape(shape.circle(center_x, center_y, radius))
            screen.pen = BG
            screen.shape(shape.circle(center_x, center_y, radius - 2))
        screen.pen = PURPLE
        screen.shape(shape.rounded_rectangle(center_x - 27, center_y - 20, 54, 40, 9))
        screen.pen = BG
        screen.shape(shape.circle(center_x - 10, center_y, 5))
        screen.shape(shape.circle(center_x + 10, center_y, 5))
        screen.font = BODY_FONT
        screen.pen = TEXT
        self.center("LINKED" if self.transport.connected else "READY TO CONNECT", 167)
        screen.pen = MUTED
        self.center(shorten(self.transport.laptop, 38), 187)
        self.center(shorten(self.last_repo, 46), 202)
        screen.pen = BORDER
        self.center("MENU: SAFE DEMO", 224)

    def draw_setup(self):
        self.draw_header("PAGER SETUP")
        screen.font = TITLE_FONT
        screen.pen = PURPLE
        self.center("PAIR YOUR BADGE", 58)
        screen.font = BODY_FONT
        screen.pen = TEXT
        self.center("1  Connect the badge over USB", 93)
        self.center("2  Install the desktop companion", 113)
        self.center("3  Run: copilot-pager pair", 133)
        screen.pen = PANEL
        screen.shape(shape.rounded_rectangle(35, 158, WIDTH - 70, 42, 6))
        screen.pen = MUTED
        self.center("No secrets are stored in the app", 170)
        demo_control = (
            "SELECT: preview a safe demo"
            if SIMULATOR_CONTROLS
            else "MENU: preview a safe demo"
        )
        self.center(demo_control, 187)
        if self.transport.error and self.transport.error != "Not paired":
            screen.pen = RED
            self.center(shorten(self.transport.error, 46), 215)

    def draw_request(self):
        request = self.request or {}
        self.draw_header("APPROVAL REQUEST")
        remaining = max(0, (self.deadline - badge.ticks + 999) // 1000)
        tool = shorten(request.get("tool_name", "tool").upper(), 15)
        screen.font = BODY_FONT
        screen.pen = PURPLE if request.get("allow_remote", True) else ORANGE
        screen.shape(shape.rounded_rectangle(10, 43, 91, 23, 5))
        screen.pen = BG
        screen.text(tool, 18, 49)
        screen.pen = TEXT
        screen.text(shorten(request.get("repo", "Unknown repository"), 27), 109, 48)
        screen.pen = MUTED
        timer = "%02ds" % remaining
        timer_width, _ = screen.measure_text(timer)
        screen.text(timer, WIDTH - timer_width - 11, 48)

        label, lines = self.sections[self.section] if self.sections else ("DETAILS", ["No details supplied"])
        screen.pen = PANEL
        screen.shape(shape.rounded_rectangle(9, CONTENT_TOP - 3, WIDTH - 18, CONTENT_BOTTOM - CONTENT_TOP + 6, 6))
        screen.pen = BLUE
        screen.text("%s  %d/%d" % (label, self.section + 1, len(self.sections)), 17, CONTENT_TOP + 2)
        y = CONTENT_TOP + 19
        visible = max(1, (CONTENT_BOTTOM - y) // LINE_H)
        screen.font = CODE_FONT if label in ("COMMAND", "CHANGES", "ARGUMENTS") else BODY_FONT
        for line in lines[self.scroll : self.scroll + visible]:
            screen.pen = GREEN if line.startswith("+") else RED if line.startswith("-") else TEXT
            screen.text(shorten(line, WRAP_COLUMNS + 3), 17, y)
            y += LINE_H
        if len(lines) > visible:
            track_y = CONTENT_TOP + 20
            track_h = CONTENT_BOTTOM - track_y - 5
            thumb_h = max(10, int(track_h * visible / len(lines)))
            maximum = max(1, len(lines) - visible)
            thumb_y = track_y + int((track_h - thumb_h) * self.scroll / maximum)
            screen.pen = BORDER
            screen.shape(shape.rounded_rectangle(WIDTH - 14, track_y, 3, track_h, 1))
            screen.pen = BLUE
            screen.shape(shape.rounded_rectangle(WIDTH - 14, thumb_y, 3, thumb_h, 1))
        self.draw_footer(request)

    def draw_footer(self, request):
        y = HEIGHT - FOOTER_H
        screen.pen = PANEL_2
        screen.shape(shape.rectangle(0, y, WIDTH, FOOTER_H))
        screen.font = BODY_FONT
        screen.pen = RED
        screen.text("< DENY", 10, y + 9)
        screen.pen = GREEN if request.get("allow_remote", True) else ORANGE
        approve = "HOLD SEL APPROVE" if request.get("allow_remote", True) else "SEL: LAPTOP ONLY"
        self.center(approve, y + 9)
        screen.pen = MUTED
        text = "HOLD > LAPTOP"
        width, _ = screen.measure_text(text)
        screen.text(text, WIDTH - width - 9, y + 9)
        started = self.select_started if self.select_started is not None else self.right_started
        if started is not None:
            progress = clamp((badge.ticks - started) / 1000.0, 0.0, 1.0)
            screen.pen = GREEN if self.select_started is not None else BLUE
            screen.shape(shape.rectangle(0, HEIGHT - 3, int(WIDTH * progress), 3))

    def draw_result_icon(self, center_x, center_y, kind, accent):
        screen.pen = accent
        if kind == "allow":
            for offset in (-2, -1, 0, 1, 2):
                screen.line(
                    center_x - 18,
                    center_y + offset,
                    center_x - 6,
                    center_y + 12 + offset,
                )
                screen.line(
                    center_x - 6,
                    center_y + 12 + offset,
                    center_x + 20,
                    center_y - 15 + offset,
                )
        elif kind == "deny":
            for offset in (-2, -1, 0, 1, 2):
                screen.line(
                    center_x - 15,
                    center_y - 15 + offset,
                    center_x + 15,
                    center_y + 15 + offset,
                )
                screen.line(
                    center_x + 15,
                    center_y - 15 + offset,
                    center_x - 15,
                    center_y + 15 + offset,
                )
        elif kind == "expired":
            screen.shape(shape.circle(center_x, center_y, 20))
            screen.pen = BG
            screen.shape(shape.circle(center_x, center_y, 16))
            screen.pen = accent
            screen.line(center_x, center_y, center_x, center_y - 10)
            screen.line(center_x, center_y, center_x + 9, center_y + 6)
            screen.shape(shape.circle(center_x, center_y, 2))
        elif kind == "cancelled":
            screen.shape(
                shape.rounded_rectangle(center_x - 15, center_y - 15, 30, 30, 4)
            )
        else:
            # A laptop screen with an outward arrow represents native review.
            screen.shape(
                shape.rounded_rectangle(center_x - 22, center_y - 16, 44, 29, 4)
            )
            screen.pen = BG
            screen.shape(
                shape.rounded_rectangle(center_x - 18, center_y - 12, 36, 21, 2)
            )
            screen.pen = accent
            screen.line(center_x - 26, center_y + 17, center_x + 26, center_y + 17)
            screen.line(center_x - 8, center_y - 1, center_x + 9, center_y - 1)
            screen.line(center_x + 9, center_y - 1, center_x + 2, center_y - 8)
            screen.line(center_x + 9, center_y - 1, center_x + 2, center_y + 6)

    def draw_result(self):
        self.draw_header("REQUEST CLOSED")
        kind = self.result_kind
        if kind == "allow":
            accent = GREEN
        elif kind in ("deny", "cancelled"):
            accent = RED
        elif kind == "expired":
            accent = ORANGE
        else:
            accent = BLUE
        screen.pen = accent
        screen.shape(shape.circle(WIDTH // 2, 103, 42))
        screen.pen = BG
        screen.shape(shape.circle(WIDTH // 2, 103, 34))
        self.draw_result_icon(WIDTH // 2, 103, kind, accent)
        screen.font = TITLE_FONT
        screen.pen = TEXT
        self.center(shorten(self.result.upper(), 34), 163)
        screen.font = BODY_FONT
        screen.pen = MUTED
        if self.result_demo:
            detail = "Safe demo - no command was run"
        else:
            detail = {
                "allow": "Approved once - no permission saved",
                "deny": "Copilot received your denial",
                "expired": "Request returned to your laptop",
                "cancelled": "Copilot cancelled this request",
            }.get(kind, "Continue from the laptop prompt")
        self.center(detail, 192)

    def center(self, text, y):
        width, _ = screen.measure_text(text)
        screen.text(text, (WIDTH - width) / 2, y)

    def draw(self):
        if self.state == "setup":
            self.draw_setup()
        elif self.state == "request":
            self.draw_request()
        elif self.state == "result":
            self.draw_result()
        else:
            self.draw_idle()

    def update(self):
        self.tick()
        self.draw()

    def exit(self):
        try:
            badge.caselights(0)
        except (AttributeError, ValueError):
            pass
        self.transport.stop()


app = PagerApp()


def update():
    app.update()


def on_exit():
    app.exit()


if SIMULATOR_CONTROLS:
    _simulator_run = run

    def run(update_function, on_exit=None):
        _simulator_run(update_function)


badge.default_clear = BG
run(update, on_exit=on_exit)
