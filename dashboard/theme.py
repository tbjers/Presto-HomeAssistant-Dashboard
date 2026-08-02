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
see dashboard/settings.py for where that choice is persisted.

CURRENTLY GATED OFF: loading either .af asset via PicoVector hangs real
hardware hard enough to require a physical power-cycle to recover
(confirmed on-device -- reproduces from WindowManager(theme=...)
construction alone with font_choice pre-set, independent of a separate
base_font_scale-ordering bug in setup() below that was also fixed but
wasn't the actual cause). FONT_CHOICES below only has "default" until
this is root-caused; see its own comment, and
dashboard.settings_page.FONT_CHOICE_ORDER/dashboard.settings.
VALID_FONT_CHOICES for the other two places that must move in lockstep
with it. The rest of this section describes the (currently unreachable)
vector-font mechanism as designed, for whoever re-enables it.

Rather than
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
    secondary_background_pen = palette.GRAY_950
    error_pen = palette.ROSE_600

    # font_choice -> .af asset path (None means the default font5x5 bitmap
    # font, drawn via dashboard.font rather than PicoVector at all).
    #
    # "atkinson"/"inter" are temporarily removed -- see
    # dashboard.settings_page.FONT_CHOICE_ORDER's comment for why (a
    # PicoVector .af load hangs real hardware). Keeping them out of this
    # dict, not just the Settings UI, means even a stray/foreign
    # font_choice value (e.g. a leftover settings.json from before this
    # was disabled) can't reach _vector.set_font() -- FONT_CHOICES.get()
    # just returns None and setup()/apply_font_choice() fall back to the
    # bitmap font5x5 path. Restore both entries (paths unchanged) once the
    # underlying PicoVector issue is fixed.
    FONT_CHOICES = {
        "default": None,
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
            # Theme.setup() (tmos_ui.py), called via super() below, loads
            # self.font into PicoVector itself via
            # self._vector.set_font(self.font, self.base_font_scale) --
            # using whatever base_font_scale already holds *at that point*,
            # which is still DefaultTheme.base_font_scale (1), since
            # _configure_font_metrics() (which sets it to VECTOR_FONT_SIZE)
            # doesn't run until after super().setup() returns below.
            # Loading a PicoVector .af font at a literal size of 1 locked
            # up real hardware hard enough that even USB serial stopped
            # responding -- confirmed on-device: booting with a persisted
            # vector font_choice made the Presto unrecoverable except by
            # deleting main.py from another machine. Pre-set the real
            # pixel size here so Theme.setup()'s own set_font() call
            # already gets it right; this doesn't need dpi_scale_factor
            # (unlike the default/bitmap branch in _configure_font_metrics
            # below), so it's safe to set before super().setup() runs.
            self.base_font_scale = self.VECTOR_FONT_SIZE
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
        # DefaultTheme's version (tmos_ui.py) fills the strip then draws
        # top/bottom borders via display.line() -- no left/right edge, so
        # the box wasn't closed on every side (see below), and on real
        # hardware that line()-drawn border rendered visibly thicker than
        # the 1px rectangle()-built outline
        # draw_button_frame/draw_app_switcher_button use, most obviously
        # where the two sit right next to each other around the hamburger
        # button. Redraws all four sides here as explicit 1px
        # display.rectangle() calls instead of super().draw_systray()'s
        # display.line() ones, for a border technique that's consistent
        # (and consistently 1px) with the rest of this theme's chrome.
        x, y, w, h = region
        display.set_pen(self.secondary_background_pen)
        display.rectangle(x, y, w, h)
        display.set_pen(self.foreground_pen)
        display.rectangle(x, y, w, 1)  # top
        display.rectangle(x, y + h - 1, w, 1)  # bottom
        display.rectangle(x, y, 1, h)  # left
        display.rectangle(x + w - 1, y, 1, h)  # right

    def draw_button_frame(self, display, region, is_pressed, adjoined):
        # DefaultTheme's version (tmos_ui.py) fills with foreground_pen and
        # is_pressed insets background_pen -- correct for its "black ink on
        # white paper" convention (foreground=BLACK, background=WHITE), but
        # CompressoTheme's pens are inverted (foreground_pen is the *light*
        # color used as ink on a dark page, background_pen the near-black
        # page color -- see class docstring/pen assignments above), so the
        # vendored algorithm painted unselected buttons white and selected
        # ones black. Draws an always-on foreground_pen outline first (an
        # unselected button's background_pen fill would otherwise be
        # indistinguishable from the page it sits on, which also clears to
        # background_pen), then insets the state's fill -- background_pen
        # unselected, foreground_pen selected, matching the outline so a
        # selected button reads as a solid block.
        x, y, w, h = region
        display.set_pen(self.foreground_pen)
        display.rectangle(x, y, w, h)
        display.set_pen(self.foreground_pen if is_pressed else self.background_pen)
        display.rectangle(x + 1, y + 1, w - 2, h - 2)

    def draw_button_title(self, display, region, is_pressed, title, title_rel_scale, adjoined):
        # See draw_button_frame above -- same pen swap, same reason.
        display.set_pen(self.background_pen if is_pressed else self.foreground_pen)
        self.centered_text(display, region, title, rel_scale=title_rel_scale)

    def draw_systray_page_button_frame(self, display, region, is_pressed, adjoined):
        # Base Theme.draw_systray_page_button_frame (tmos_ui.py) just calls
        # draw_button_frame above -- fine for a one-off selection like the
        # settings radio groups, but the "current page" tab is *always*
        # is_pressed, so that full foreground_pen block would be a
        # permanently-lit bright patch sitting in the middle of the (dark)
        # systray. A thin underline reads as "this is the current page"
        # without turning part of the systray into a standing bright spot.
        if not is_pressed:
            return
        # This region shares the systray's own y/height (Systray hands
        # accessories/the page switcher the full strip height -- see
        # dashboard.app_manager.DashboardAppManagerAccessory's docstring),
        # so its bottom row is the exact same row draw_systray() draws its
        # 1px border on. A 2px-tall underline flush against that row (1px
        # of its own + the shared border row) reads as the systray's
        # border having doubled to 2px specifically under the current
        # page's tab -- confirmed on real hardware. Leaving a gap (plain
        # systray fill) between the border and this underline keeps them
        # visually distinct instead of merging into one thick line.
        display.set_pen(self.foreground_pen)
        x, y, w, h = region
        border_height = 1
        gap = 2
        underline_height = 2
        display.rectangle(x, y + h - border_height - gap - underline_height, w, underline_height)

    def draw_systray_page_button_title(
        self, display, region, is_pressed, title, title_rel_scale, adjoined
    ):
        # See draw_systray_page_button_frame above -- titles stay
        # foreground_pen regardless of state (always legible against the
        # systray's own dark fill), with the underline being the only
        # current-page indicator.
        display.set_pen(self.foreground_pen)
        self.centered_text(display, region, title, rel_scale=title_rel_scale)

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
        # Unlike DefaultTheme's version, this button also gets the same
        # foreground_pen outline draw_button_frame gives every other button
        # -- without it, the icon was just three bars floating on the plain
        # systray fill with no boundary of its own, inconsistent with every
        # other now-outlined button.
        rx, ry, rw, rh = region
        display.set_pen(self.foreground_pen)
        display.rectangle(rx, ry, rw, rh)
        display.set_pen(self.background_pen)
        display.rectangle(rx + 1, ry + 1, rw - 2, rh - 2)

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
