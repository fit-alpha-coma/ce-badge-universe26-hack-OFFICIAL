# Control mapping on the badge's logical actions. The touch face and the
# physical switches report the same actions, and every race control has a
# switch: Left/Right steer, Select fires, Up drifts, Down brakes. BACK also
# drifts so touch players keep a thumb on each side of the face.

import math

# On-screen labels, the same as the firmware's input test app uses.
LABEL = {"SELECT": "SEL", "BACK": "BK", "MENU": "MN", "HOME": "HM"}


class Controls:
    def __init__(self):
        self.tilt = False
        self.tilt_zero = 0.0
        self.steer = 0.0

    def calibrate(self):
        ax, ay, az, _gx, _gy, _gz = badge.imu()
        g = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
        self.tilt_zero = ax / g

    def race(self, dt, assist):
        """(steer, brake, drift_held, use_item, assist) for this frame."""
        held = badge.held()
        target = (BUTTON_RIGHT in held) - (BUTTON_LEFT in held)
        if self.tilt and not target:
            ax, ay, az, _gx, _gy, _gz = badge.imu()
            g = math.sqrt(ax * ax + ay * ay + az * az) or 1.0
            t = (ax / g - self.tilt_zero) / 0.35
            target = -1.0 if t < -1 else (1.0 if t > 1 else t)
            if abs(target) < 0.08:
                target = 0.0
            self.steer = target
        else:
            # ease toward full lock so a tap is a small correction
            rate = 8.0 * dt
            if self.steer < target:
                self.steer = min(target, self.steer + rate)
            elif self.steer > target:
                self.steer = max(target, self.steer - rate)
            if target == 0 and abs(self.steer) < 0.05:
                self.steer = 0.0
        drift = BUTTON_BACK in held or BUTTON_UP in held
        brake = BUTTON_DOWN in held
        use = badge.pressed(BUTTON_SELECT)
        return self.steer, brake, drift, use, assist and not self.tilt


def menu_move():
    """-1 / +1 for Up / Down presses in a vertical list, else 0."""
    if badge.pressed(BUTTON_UP):
        return -1
    if badge.pressed(BUTTON_DOWN):
        return 1
    return 0


def back(alt):
    """BACK is a touch pad only; `alt` is the switch that also goes back on
    this screen, so the game is fully usable from the physical switches."""
    return badge.pressed(BUTTON_BACK) or badge.pressed(alt)


def chord():
    """Up + Down together, the physical-switch stand-in for MENU and BACK
    (both touch-only). True on the frame the second switch goes down."""
    held = badge.held()
    if BUTTON_UP in held and BUTTON_DOWN in held:
        return badge.pressed(BUTTON_UP) or badge.pressed(BUTTON_DOWN)
    return False
