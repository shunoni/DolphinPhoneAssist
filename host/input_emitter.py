"""
DolphinPhoneAssist - Virtual Input Emitter (Keyboard & Mouse Mode)
Simulates Dolphin's default Wiimote Keyboard & Mouse profile on Linux using uinput/evdev.
Provides fallback for testing environments.
"""

import sys
import time

HAS_EVDEV = False
try:
    import evdev
    from evdev import UInput, ecodes as e
    HAS_EVDEV = True
except ImportError:
    pass

class InputEmitter:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.uinput = None
        self.last_pointer = {"x": 0.0, "y": 0.0}
        self.screen_width = 1920
        self.screen_height = 1080
        
        if self.enabled and HAS_EVDEV:
            self._init_evdev()
        else:
            if not HAS_EVDEV:
                print("[Input] 'evdev' module not detected (standard for Linux/PiOS). Running in simulated mode.")

    def _init_evdev(self):
        try:
            capabilities = {
                e.EV_KEY: [
                    # Dolphin Wiimote Default Keys
                    e.KEY_UP, e.KEY_DOWN, e.KEY_LEFT, e.KEY_RIGHT, # D-Pad
                    e.KEY_X, e.KEY_Z,                              # A and B buttons (or clicks)
                    e.KEY_Q, e.KEY_E,                              # Minus and Plus
                    e.KEY_H,                                       # Home
                    e.KEY_1, e.KEY_2,                              # 1 and 2
                    e.BTN_LEFT, e.BTN_RIGHT                        # Mouse Buttons
                ],
                e.EV_REL: [
                    e.REL_X, e.REL_Y                               # Relative Mouse for IR Pointer
                ]
            }
            self.uinput = UInput(capabilities, name="DolphinPhoneAssist-VirtualWiimote")
            print("[Input] Linux virtual keyboard & mouse device successfully created (/dev/uinput)!")
        except PermissionError:
            print("[Input] Permission denied opening /dev/uinput.")
            print("[Input] Hint: Run 'sudo usermod -aG input $USER' and restart session or use the installer.")
            self.uinput = None
        except Exception as ex:
            print(f"[Input] Could not initialize uinput: {ex}")
            self.uinput = None

    def handle_button(self, key, state):
        if not self.uinput:
            return

        # Key mapping to Dolphin stock profile
        # Up/Down/Left/Right -> Arrow Keys
        # A -> Left Click (or X)
        # B -> Right Click (or Z)
        # Minus -> Q
        # Plus -> E
        # Home -> H
        # 1 -> 1
        # 2 -> 2
        key_map = {
            "up": (e.EV_KEY, e.KEY_UP),
            "down": (e.EV_KEY, e.KEY_DOWN),
            "left": (e.EV_KEY, e.KEY_LEFT),
            "right": (e.EV_KEY, e.KEY_RIGHT),
            "a": (e.EV_KEY, e.BTN_LEFT),
            "b": (e.EV_KEY, e.BTN_RIGHT),
            "minus": (e.EV_KEY, e.KEY_Q),
            "plus": (e.EV_KEY, e.KEY_E),
            "home": (e.EV_KEY, e.KEY_H),
            "one": (e.EV_KEY, e.KEY_1),
            "two": (e.EV_KEY, e.KEY_2)
        }

        if key in key_map:
            ev_type, ev_code = key_map[key]
            val = 1 if state else 0
            self.uinput.write(ev_type, ev_code, val)
            self.uinput.syn()

    def handle_pointer(self, pointer_x, pointer_y):
        if not self.uinput:
            return

        # Convert pointer coordinates [-1.0, 1.0] to relative deltas
        dx = (pointer_x - self.last_pointer["x"]) * 80.0
        dy = (pointer_y - self.last_pointer["y"]) * 80.0

        self.last_pointer["x"] = pointer_x
        self.last_pointer["y"] = pointer_y

        idx = int(round(dx))
        idy = int(round(dy))

        if idx != 0 or idy != 0:
            if idx != 0:
                self.uinput.write(e.EV_REL, e.REL_X, idx)
            if idy != 0:
                self.uinput.write(e.EV_REL, e.REL_Y, idy)
            self.uinput.syn()

    def close(self):
        if self.uinput:
            try:
                self.uinput.close()
            except Exception:
                pass
