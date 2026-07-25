# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
On-device smoke test for dashboard.font5x5/dashboard.font/CompressoTheme's
text() override -- NOT part of the app. Run via `mpremote run` (does not
persist to flash). Draws the same "07:09"/"ARBEITSZEIT"-shaped sample text
CompressoTheme.text() would draw for tiles.py's ValueTile/DateTimeTile, at
the actual rel_scale values tiles.py uses, so the result can be visually
compared against the compresto reference screenshot's measured 30px value
digits / 10px label height.
"""

from tmos import OS
from tmos_ui import WindowManager
from dashboard.theme import CompressoTheme

os = OS(layers=1, full_res=True)
wm = WindowManager(os, theme=CompressoTheme())
# Constructing WindowManager already called theme.setup(display, dpi_scale_factor=2).
theme = wm.theme
display = os.display

theme.clear_display(display)

display.set_pen(theme.foreground_pen)
theme.text(display, "07:09", 20, 20, rel_scale=3)
theme.text(display, "ARBEITSZEIT", 20, 60, rel_scale=1)
theme.text(display, "abc/xyz", 20, 90, rel_scale=1)
theme.text(display, "12-34—56/78", 20, 110, rel_scale=1)

w, h = theme.measure_text(display, "07:09", rel_scale=3)
print("measure_text('07:09', rel_scale=3) =", (w, h), "-- expect (156, 30)")
print("base_font_scale =", theme.base_font_scale, "-- expect 2")
print("base_text_height =", theme.base_text_height, "-- expect 10")
print("base_line_height =", theme.base_line_height, "-- expect 14")

os.update_display()
print("Drawn -- check screen for 30px-tall '07:09' and 10px-tall 'ARBEITSZEIT'/'ABC XYZ'.")
