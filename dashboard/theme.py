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

Font choice: font5x5 (above) is the only font drawn until the user opens
the new Settings app (dashboard/settings_page.py, reached via the existing
hamburger/app-switcher systray accessory) and picks one of FONT_CHOICES'
two PicoVector .af assets (Atkinson Hyperlegible, Inter) --
see dashboard/settings.py for where that choice is persisted. Rather than
building a second, separate PicoVector instance the way dashboard/modal.py's
controls each do for their own shapes, font rendering reuses TmOS's own
already-built-in .af loading path (tmos_ui.py's Theme.setup()/.text()/
.measure_text(), gated on self.font.endswith(".af") -- confirmed real,
working infrastructure, just unused by any theme in this repo until now):
setup() sets self.font to the chosen .af path *before* calling
super().setup(), so Theme's own dispatch logic loads it into self._vector
and flips self._use_vector_font_rendering; text()/measure_text() below then
only need to choose between font.draw_text/measure_text (font_choice ==
"default") and super().text()/measure_text() (anything else) -- no
reimplementation of TmOS's vector-font handling.

font_choice must be set as an instance attribute (see
apply_font_choice()/main.py) *before* setup() runs, since Theme.setup() is
a one-shot (tmos_ui.py: "if self._setup_done: ...; return" on any call
after the first) -- switching fonts later at runtime goes through
apply_font_choice() instead, which re-does just the font-loading piece
setup() can no longer repeat.

base_font_scale means something different for each rendering path, and
switching font_choice must switch what it's set to, not just leave
whatever Theme.setup()'s automatic dpi-scaling left there. text_scale()
(tmos_ui.py) computes `round(base_font_scale * rel_scale)` and hands that
straight to either PicoGraphics' bitmap text (where it's a *multiplier* on
an 8-row glyph -- small integers, e.g. 2) or PicoVector's
set_font_size()/set_font() (where it's a literal *pixel* font size --
needs to be ~16px+ to be legible, not 2-6px). Reusing font5x5's tuned
value of 2 for a vector font would render it at ~2px: technically not
broken, but silently unreadable. _configure_font_metrics() below picks
between two independently-tuned sets of base_font_scale/base_text_height/
base_line_height depending on font_choice, called from both setup() and
apply_font_choice() so switching either direction at runtime re-derives
the right values, not just whichever set happened to be loaded at boot.

VECTOR_FONT_SIZE/_CAP_HEIGHT_RATIO/_LINE_HEIGHT_RATIO approximate font5x5's
observed proportions (10px cap height at rel_scale=1, see above) using
typical typographic ratios (cap-height ~0.7x font-size, line-height ~1.2x)
since Atkinson Hyperlegible/Inter's actual metrics haven't been measured
against real PicoVector output yet -- needs on-device tuning once that's
possible (see scripts/settings_smoke_test.py).

corner_style/corner_radius: dashboard/modal.py's VerticalSliderControl/
PowerButton compute their actual corner radius, in px, as
`dashboard.corners.radius_blocks(theme.corner_radius) * theme.text_scale(3)`
-- i.e. a whole number of the same "pixel" unit dashboard.font5x5's big
tile-value text (ValueTile/TemperatureTile/DateTimeTile, all rel_scale=3)
already draws at, so a rounded corner reads as an integer count of the
same visual "pixels" as the rest of this retro-styled UI, rather than an
arbitrary unrelated px count -- and, since text_scale(3) is theme's own
method, this stays correct automatically if font_choice switches to a
vector font with different metrics (see dashboard/corners.py's module
docstring for the block-count -> px mapping and the staircase geometry).
"""

from tmos_ui import DefaultTheme

from dashboard import font, font5x5, grid, palette


class CompressoTheme(DefaultTheme):
    background_pen = palette.GRAY_950
    foreground_pen = palette.GRAY_200
    secondary_background_pen = palette.GRAY_900
    error_pen = palette.ROSE_600

    # font_choice -> .af asset path (None means the default font5x5 bitmap
    # font, drawn via dashboard.font rather than PicoVector at all).
    FONT_CHOICES = {
        "default": None,
        "atkinson": "dashboard/assets/atkinson-hyperlegible.af",
        "inter": "dashboard/assets/inter.af",
    }

    # corner_style picks the rendering technique (smooth PicoVector
    # antialiasing vs blocky pixel-block notches, dashboard/corners.py);
    # corner_radius picks the size, in dashboard.corners.RADIUS_CHOICES
    # steps -- both are orthogonal, plain instance-level knobs read
    # directly by dashboard/modal.py's controls and
    # dashboard/settings_page.py, not part of Theme's pen/dpi-scaling
    # machinery. main.py overrides all three (font_choice, corner_style,
    # corner_radius) from the persisted settings file (font_choice must be
    # set before setup() runs -- see module docstring; the corner knobs
    # have no such constraint).
    CORNER_STYLE_CHOICES = ("smooth", "blocky")

    font_choice = "default"
    corner_style = "smooth"
    corner_radius = "large"

    # See module docstring -- a literal pixel font size for PicoVector, not
    # a bitmap-font scale multiplier. Placeholder pending on-device tuning.
    VECTOR_FONT_SIZE = 16
    VECTOR_FONT_CAP_HEIGHT_RATIO = 0.7
    VECTOR_FONT_LINE_HEIGHT_RATIO = 1.2

    def setup(self, display, dpi_scale_factor):
        path = self.FONT_CHOICES.get(self.font_choice)
        if path:
            self.font = path
        super().setup(display, dpi_scale_factor)
        self.padding = grid.GAP
        self.systray_height = round(grid.span_size(grid.tile_size(480), 2))
        self._configure_font_metrics(display, path)

    def apply_font_choice(self, display, font_choice):
        """
        Switches the active font at runtime (called from
        dashboard.settings_page.SettingsPage), without a reboot --
        Theme.setup() (tmos_ui.py) is one-shot, so this re-does just the
        font-loading piece of it directly instead.
        """
        self.font_choice = font_choice if font_choice in self.FONT_CHOICES else "default"
        path = self.FONT_CHOICES[self.font_choice]
        self.font = path or DefaultTheme.font
        self._configure_font_metrics(display, path)

    def _configure_font_metrics(self, display, path):
        """
        Sets self.font/base_font_scale/base_text_height/base_line_height
        for whichever rendering path `path` (a FONT_CHOICES value) selects,
        and loads the .af file into PicoVector if it's set. Called from
        both setup() and apply_font_choice() so switching font_choice
        either direction -- at boot or live -- always re-derives the right
        metrics, rather than an apply_font_choice() call reusing whatever
        the *other* path's setup() happened to leave behind.
        """
        self._use_vector_font_rendering = bool(path)
        if path:
            self.base_font_scale = self.VECTOR_FONT_SIZE
            self.base_text_height = round(self.VECTOR_FONT_SIZE * self.VECTOR_FONT_CAP_HEIGHT_RATIO)
            self.base_line_height = round(self.VECTOR_FONT_SIZE * self.VECTOR_FONT_LINE_HEIGHT_RATIO)
            self._ensure_picovector(display)
            self._vector.set_font(self.font, self.base_font_scale)
        else:
            # DefaultTheme.base_font_scale, scaled the same way Theme.setup()
            # (tmos_ui.py) itself would -- restores the exact value setup()
            # left in place for the default choice, even when this runs from
            # apply_font_choice() well after boot, switching back from a
            # vector font that overwrote it above.
            self.base_font_scale = DefaultTheme.base_font_scale * self.dpi_scale_factor
            self.base_text_height = font5x5.CELL_HEIGHT * self.base_font_scale
            self.base_line_height = font5x5.LINE_HEIGHT * self.base_font_scale

    def measure_text(self, display, text, rel_scale=1):
        if self.font_choice == "default":
            return font.measure_text(text, self.text_scale(rel_scale))
        return super().measure_text(display, text, rel_scale=rel_scale)

    def text(self, display, text, x, y, *args, rel_scale=1.0, **kwargs):
        if self.font_choice == "default":
            font.draw_text(display, text, x, y, self.text_scale(rel_scale))
        else:
            super().text(display, text, x, y, *args, rel_scale=rel_scale, **kwargs)

    def draw_systray(self, display, region, adjoined):
        # DefaultTheme only draws top/bottom border lines across the full
        # strip -- there's no left/right edge closing the box. The rightmost
        # page button's own solid fill happens to reach the screen's right
        # edge, so that side looks closed by coincidence, but the leading
        # app-switcher accessory has no fill of its own (just its hamburger
        # bars on the plain strip background), so the left edge read as an
        # open/"clipped" border. Add both verticals so the box is closed on
        # every side regardless of what's docked at either end.
        super().draw_systray(display, region, adjoined)
        display.set_pen(self.foreground_pen)
        right_x = region.x + region.width - 1
        bottom_y = region.y + region.height - 1
        display.line(region.x, region.y, region.x, bottom_y)
        display.line(right_x, region.y, right_x, bottom_y)

    def draw_app_switcher_button(self, display, region, is_pressed):
        # Copy of DefaultTheme.draw_app_switcher_button (tmos_ui.py) with an
        # extra 1px of left inset. The left border draw_systray() now paints
        # sits on this button's own leftmost column, which used to be plain
        # background -- so the hamburger bars ended up 1px closer to that
        # border than to the DASHBOARD button's edge on the right (confirmed
        # by pixel-measuring a photo: ~7 device px left vs ~8 right). The
        # right side has no equivalent border baked into ITS margin (the
        # DASHBOARD button's fill starts immediately after, not within, the
        # gap), so only the left inset needs the extra pixel.
        num_bars = 3
        spacing = 3 * self.dpi_scale_factor
        left_inset = spacing + 1
        v_inset = spacing
        x = region.x + left_inset
        y = region.y + spacing + v_inset
        width = region.width - left_inset - spacing
        available_height = region.height - spacing - v_inset - v_inset - spacing
        total_bar_height = available_height - (spacing * (num_bars - 1))
        bar_height = int(round(total_bar_height / num_bars))
        display.set_pen(self.background_pen if is_pressed else self.foreground_pen)
        for _ in range(num_bars):
            display.rectangle(x, y, width, bar_height)
            y += bar_height + spacing
