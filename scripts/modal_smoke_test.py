# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
On-device smoke test for the redesigned dimmable-light modal (vertical
no-handle slider + mdiPower toggle) -- NOT part of the app, doesn't touch
flash/main.py. Run via `mpremote run scripts/modal_smoke_test.py` after
copying tmos.py/tmos_ui.py/tmos_apps.py/tmos_themes.py/umqtt/dashboard/ to
the device.

Proves two things host-side pytest cannot:

1. dashboard.icons still imports fast after adding MDI_POWER_OUTLINE (see
   CLAUDE.md's MicroPython-compiler literal-count note) -- prints the
   import time in ms.
2. LightBrightnessModal.setup()/_draw()/each control's draw() run against
   the *real* PicoGraphics/PicoVector without raising -- in particular
   that Polygon.rectangle(..., corners=...) accepts the vertical slider's
   rounded track/fill and the power button's capsule background, and that
   the flattened MDI_POWER_OUTLINE polygon.path() call doesn't error.

Draws the modal once directly (bypassing WindowManager.show_modal_page,
which would need a running app/page underneath) and flips it to screen,
then exits -- unlike preview_main.py, this doesn't enter the blocking run
loop, so it's a fast, hands-off pass/fail check. Leaves the drawn modal on
screen for a visual check afterwards.
"""

import time

_start = time.ticks_ms()
import dashboard.icons  # noqa: E402 -- timed import, must come first
_icons_import_ms = time.ticks_diff(time.ticks_ms(), _start)
print("dashboard.icons import took {}ms".format(_icons_import_ms))

from tmos import OS, Region  # noqa: E402
from tmos_ui import WindowManager  # noqa: E402

from dashboard.modal import LightBrightnessModal  # noqa: E402
from dashboard.palette import PenCache  # noqa: E402
from dashboard.theme import CompressoTheme  # noqa: E402


class FakeMQTT:
    def publish(self, topic, payload):
        print("publish {} {}".format(topic, payload))


os_ = OS(layers=1, full_res=True)
wm = WindowManager(os_, theme=CompressoTheme())
pens = PenCache(os_.display)

modal = LightBrightnessModal(
    "light", "ceiling", "CEILING", FakeMQTT(), pens,
    initial_brightness=180, initial_state=True,
)

region = Region(0, 0, *os_.display.get_bounds())
modal.setup(region, wm)
print("slider region:", modal._slider.region)
print("power button region:", modal._power_button.region)
print("label region:", modal._label_region)
print("percentage text (on, 180/255):", modal._percentage_text())

modal._update(os_)
modal._draw(os_.display, region, wm.theme)
for control in modal._controls:
    control.draw(os_.display, wm.theme)
os_.update_display()

print("Modal drew without raising -- check the screen.")

# Now flip to the off state and redraw, to sanity check the OFF label path
# and the power button's off tint too.
modal._is_on = False
modal._update(os_)
time.sleep_ms(1500)
modal._draw(os_.display, region, wm.theme)
for control in modal._controls:
    control.draw(os_.display, wm.theme)
os_.update_display()
print("Redrew in OFF state -- check the screen.")
print("percentage text (off):", modal._percentage_text())
