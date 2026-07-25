# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Boot splash screen -- an mdiHomeAssistant icon + label, shown while
main.py's wifi/NTP connect (os.boot(wifi=True, ...) blocks synchronously
for this) and app setup happen.

show(os) must be called right after constructing OS() (which is all that's
needed -- OS.__init__ already sets up os.presto/os.display) and before
os.boot(), so something appears immediately rather than a blank screen for
however long the network takes. Nothing else touches the display until the
WindowManager run loop starts ticking pages, so this needs no explicit
teardown -- DashboardPage's first tick fully repaints the screen (see
dashboard/page.py's _draw, which calls theme.clear_display() before
drawing tiles).
"""

from picovector import ANTIALIAS_BEST, PicoVector, Polygon, Transform

from dashboard import palette
from dashboard.icons import HOME_ASSISTANT_DOTS, HOME_ASSISTANT_OUTLINE, HOME_ASSISTANT_VIEWBOX

_ICON_SIZE = 200  # on-screen icon size, in pixels
_ICON_COLOR = (17, 189, 242)  # Home Assistant brand blue, #11bdf2 -- not in
# dashboard.palette, which is compresto's verbatim-ported palette rather
# than a place for brand-specific one-offs.
_LABEL = "Home Assistant"
_LABEL_SCALE = 4
_LABEL_GAP = 28  # space between icon and label


def show(os):
    """Draws the splash directly to os.display and flips it to screen."""
    display = os.display
    width, height = display.get_bounds()

    background_pen = display.create_pen(*palette.GRAY_950)
    icon_pen = display.create_pen(*_ICON_COLOR)
    label_pen = display.create_pen(*palette.WHITE)

    display.set_pen(background_pen)
    display.clear()

    label_height = 8 * _LABEL_SCALE  # bitmap8's base glyph height is 8px
    block_height = _ICON_SIZE + _LABEL_GAP + label_height
    block_top = (height - block_height) // 2

    _draw_icon(display, x=(width - _ICON_SIZE) // 2, y=block_top, pen=icon_pen)

    display.set_font("bitmap8")
    display.set_pen(label_pen)
    label_width = display.measure_text(_LABEL, _LABEL_SCALE)
    display.text(
        _LABEL,
        (width - label_width) // 2,
        block_top + _ICON_SIZE + _LABEL_GAP,
        scale=_LABEL_SCALE,
    )

    os.update_display()


def _draw_icon(display, x, y, pen):
    """
    Draws the mdiHomeAssistant glyph, scaled from its native 24x24 viewBox
    to _ICON_SIZE and positioned with its top-left corner at (x, y).
    """
    vector = PicoVector(display)
    vector.set_antialiasing(ANTIALIAS_BEST)
    vector.set_transform(Transform())

    scale = _ICON_SIZE / HOME_ASSISTANT_VIEWBOX

    icon = Polygon()
    icon.path(*((x + px * scale, y + py * scale) for px, py in HOME_ASSISTANT_OUTLINE))
    for cx, cy, r in HOME_ASSISTANT_DOTS:
        icon.circle(x + cx * scale, y + cy * scale, r * scale)

    display.set_pen(pen)
    vector.draw(icon)
