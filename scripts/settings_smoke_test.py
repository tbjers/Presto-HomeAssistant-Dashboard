# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
On-device smoke test for the new local-settings feature (blocky corner
rendering, .af font switching, settings.json persistence) -- NOT part of
the app, doesn't touch main.py. Run via `mpremote run
scripts/settings_smoke_test.py` after copying
tmos.py/tmos_ui.py/tmos_apps.py/tmos_themes.py/umqtt/dashboard/ to the
device.

Proves three things host-side pytest cannot (host tests mock picographics/
picovector entirely -- see CLAUDE.md's testing section):

1. dashboard.corners.draw_blocky_corners() actually paints a sane-looking
   pixel-block staircase against the *real* PicoGraphics.rectangle() at
   every corner_radius choice, not just that the right calls happen (see
   VerticalSliderControl/PowerButton in dashboard/modal.py). Draws the
   dimmable-light modal once per (style, radius) combination and leaves
   the last one on screen.
2. dashboard/assets/atkinson-hyperlegible.af and inter.af actually load
   via the real PicoVector.set_font()/CompressoTheme.apply_font_choice(),
   and text drawn/measured through them doesn't raise -- confirms the
   converted font files (see VENDORING.md's "Fonts" entry) are valid on
   real firmware, not just well-formed enough for host-side mocks.
3. dashboard.settings.save()/load() round-trip through the device's own
   filesystem (not a tmp_path fixture) -- confirms `open(path, "w")`/
   `json.dump` actually work against MicroPython's flash-backed FS.

Leaves the last (style, radius) combination's modal on screen for a
visual check afterwards -- doesn't enter the blocking run loop.
"""

import time

from tmos import OS, Region
from tmos_ui import WindowManager

from dashboard import corners, settings
from dashboard.modal import LightBrightnessModal
from dashboard.palette import PenCache
from dashboard.theme import CompressoTheme


class FakeMQTT:
    def publish(self, topic, payload):
        print("publish {} {}".format(topic, payload))


# 1. Settings persistence against the real filesystem.
# ---------------------------------------------------------------------
TEST_SETTINGS_PATH = "settings_smoke_test.json"
written = settings.save({"corner_style": "blocky", "corner_radius": "small", "font_choice": "inter"},
                         TEST_SETTINGS_PATH)
reloaded = settings.load(TEST_SETTINGS_PATH)
assert reloaded == written == {
    "corner_style": "blocky", "corner_radius": "small", "font_choice": "inter",
}
print("settings.save()/load() round-tripped via the real filesystem: OK")


# 2. Corner rendering, at every style x radius combination, against real
# PicoGraphics/PicoVector.
# ---------------------------------------------------------------------
os_ = OS(layers=1, full_res=True)
theme = CompressoTheme()
wm = WindowManager(os_, theme=theme)
pens = PenCache(os_.display)
region = Region(0, 0, *os_.display.get_bounds())

for style in CompressoTheme.CORNER_STYLE_CHOICES:
    for radius in corners.RADIUS_CHOICES:
        theme.corner_style = style
        theme.corner_radius = radius
        modal = LightBrightnessModal(
            "light", "ceiling", "CEILING", FakeMQTT(), pens,
            initial_brightness=180, initial_state=True,
        )
        modal.setup(region, wm)
        modal._update(os_)
        modal._draw(os_.display, region, wm.theme)
        for control in modal._controls:
            control.draw(os_.display, wm.theme)
        os_.update_display()
        print("style={} radius={} drew without raising -- check the screen.".format(style, radius))
        time.sleep_ms(1000)

theme.corner_style = "smooth"  # leave the screen on the default look
theme.corner_radius = "large"


# 3. Real .af font loading + text rendering/measurement via PicoVector.
# ---------------------------------------------------------------------
for choice in ("atkinson", "inter", "default"):
    theme.apply_font_choice(os_.display, choice)
    assert theme.font_choice == choice
    width, height = theme.measure_text(os_.display, "Settings 123", rel_scale=2)
    print("font '{}' measure_text -> ({}, {})".format(choice, width, height))

    os_.display.set_pen(theme.background_pen)
    os_.display.clear()
    os_.display.set_pen(theme.foreground_pen)
    theme.text(os_.display, "Settings 123", 20, 200, rel_scale=2)
    os_.update_display()
    print("font '{}' drew without raising -- check the screen.".format(choice))
    time.sleep_ms(1200)

print("All settings smoke checks passed.")
