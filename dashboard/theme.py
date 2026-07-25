# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
CompressoTheme(DefaultTheme) — a TmOS Theme subclass giving the systray and
any other native TmOS chrome a look consistent with the tile grid, instead
of DefaultTheme's white background clashing with a black dashboard. Tiles
themselves are drawn directly from dashboard.palette (which has far more
colors than Theme's 4 semantic pens) — this theme only governs TmOS's own
native rendering (systray, page/app-switcher buttons).

Assumes the app always boots with full_res=True (see main.py), so
display.get_bounds() is always (480, 480) and dpi_scale_factor is always 2.
dashboard.grid's GAP/COLUMNS constants are tuned specifically for that
480px-wide regime and would be unusably cramped at the 240px reference
resolution TmOS itself uses for Theme's automatic dpi-scaling (padding and
systray_height are in Theme._dpi_scaled_sizes and get multiplied by
dpi_scale_factor during setup() — rather than working out what reference
value scales up to our desired final pixel value, we just set them directly
after calling the base setup()).

Font: PicoGraphics's built-in "bitmap8" is an 8-row glyph; compresto's own
reference look (verified by pixel-scanning its screenshot) is a much
blockier 5-row font. Drawing bitmap8 at a scale chosen to match compresto's
per-row pixel size made every glyph 8/5 (1.6x) taller than intended. Fixed
by replacing bitmap8 with dashboard.font5x5 (a 5x5-ish pixel font hand-drawn
in Aseprite by the project owner — see that module's docstring), rendered
via dashboard.font's draw_text()/measure_text() (display.rectangle() calls,
not PicoGraphics' font machinery) and adapted to Theme's rel_scale here.
Overriding at the Theme level (rather than e.g. tiles.py calling
dashboard.font directly) means every caller that already goes through
theme.text()/measure_text() — tiles, centered_text/wrapped_text, button
titles, the systray clock — gets the new font for free. dashboard.splash
(which runs before there's a Theme to use) calls dashboard.font directly
instead.

base_font_scale is deliberately NOT pinned like padding/systray_height:
TmOS's automatic dpi-scaling of it (1 -> 2 at our fixed dpi_scale_factor=2)
is exactly right for a 5-row font at rel_scale=1 to reproduce compresto's
observed proportions (confirmed by pixel-measuring both the value digits
and the ARBEITSZEIT label in the reference screenshot: 5 rows * 2 = 10px
label height, 5 rows * 6 = 30px value height at tiles.py's rel_scale=3).
base_text_height/base_line_height, however, describe the *old* 8-row
bitmap8 metrics (8/10) and must be re-pinned the same way padding/
systray_height are, to reflect font5x5's actual 5-row glyph height and its
own LINE_HEIGHT (the vertical pitch for multi-line text).
"""

from tmos_ui import DefaultTheme

from dashboard import font, font5x5, grid, palette


class CompressoTheme(DefaultTheme):
    background_pen = palette.GRAY_950
    foreground_pen = palette.GRAY_200
    secondary_background_pen = palette.GRAY_900
    error_pen = palette.ROSE_600

    def setup(self, display, dpi_scale_factor):
        super().setup(display, dpi_scale_factor)
        self.padding = grid.GAP
        self.systray_height = round(grid.span_size(grid.tile_size(480), 2))
        self.base_text_height = font5x5.CELL_HEIGHT * self.base_font_scale
        self.base_line_height = font5x5.LINE_HEIGHT * self.base_font_scale

    def measure_text(self, display, text, rel_scale=1):
        return font.measure_text(text, self.text_scale(rel_scale))

    def text(self, display, text, x, y, *args, rel_scale=1.0, **kwargs):
        font.draw_text(display, text, x, y, self.text_scale(rel_scale))
