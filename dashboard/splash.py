# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Boot splash screen -- the Home Assistant logotype + label + a live status
line, shown while main.py's wifi/NTP connect (os.boot(wifi=True, ...)
blocks synchronously for this) and app setup happen.

show(os) must be called right after constructing OS() (which is all that's
needed -- OS.__init__ already sets up os.presto/os.display) and before
os.boot(), so something appears immediately rather than a blank screen for
however long the network takes. Nothing else touches the display until the
WindowManager run loop starts ticking pages, so this needs no explicit
teardown -- DashboardPage's first tick fully repaints the screen (see
dashboard/page.py's _draw, which calls theme.clear_display() before
drawing tiles).

The status line (bottom of the screen) is how you tell *where* a boot
hang is: main.py calls set_status() at each pre-os.boot() milestone, and
boot_message_handler() -- registered via os.add_message_handler just
before os.boot() -- forwards TmOS's own boot messages ("Connecting to
WiFI", "Setting time") to it, then goes inert once the run loop starts.
So a device frozen on "CONNECTING TO WIFI" tells you the hang is in
presto.connect(), not somewhere you'd have to guess at.
"""

from tmos import MSG_INFO

from dashboard import font, font5x5, palette
from dashboard.logo import BLUE, BLUE_ROWS, HEIGHT as _LOGO_NATIVE_SIZE, WHITE_ROWS

_LOGO_SCALE = 7  # integer upscale, keeps the source art's pixel edges crisp
# -- 32 * 7 = 224px, ~47% of the 480px display (about half, per the source
# asset being authored as a 32x32 sprite meant for blocky nearest-neighbor
# scaling rather than smooth resampling).
_LOGO_SIZE = _LOGO_NATIVE_SIZE * _LOGO_SCALE
_LABEL = "Booting Interface"  # font5x5 has no lowercase, draw_text() upper()s it
_LABEL_SCALE = 2  # matches tiles.py's rel_scale=1 label size (see theme.py)
_LABEL_GAP = 28  # space between logo and label

_STATUS_SCALE = 2
_STATUS_BOTTOM_MARGIN = 30  # gap between the status line and the screen edge

# tmos.OS.run_async posts this exactly once, immediately before the run
# loop starts ticking pages -- our cue to stop drawing to a screen the
# dashboard is about to own.
_RUN_LOOP_STARTED_MSG = "Starting tasks"

_ctx = None  # geometry + cached pens, populated by show()
_boot_messages_active = False


def show(os, status="Starting"):
    """Draws the splash directly to os.display and flips it to screen."""
    global _ctx
    display = os.display
    width, height = display.get_bounds()

    background_pen = display.create_pen(*palette.GRAY_950)
    blue_pen = display.create_pen(*BLUE)
    white_pen = display.create_pen(*palette.WHITE)
    label_pen = display.create_pen(*palette.GRAY_500)
    status_pen = display.create_pen(*palette.GRAY_400)

    status_height = font5x5.CELL_HEIGHT * _STATUS_SCALE
    _ctx = {
        "display": display,
        "width": width,
        "background_pen": background_pen,
        "status_pen": status_pen,
        "status_y": height - _STATUS_BOTTOM_MARGIN - status_height,
        "status_height": status_height,
    }

    display.set_pen(background_pen)
    display.clear()

    label_height = font5x5.CELL_HEIGHT * _LABEL_SCALE
    block_height = _LOGO_SIZE + _LABEL_GAP + label_height
    block_top = (height - block_height) // 2

    _draw_logo(display, x=(width - _LOGO_SIZE) // 2, y=block_top, blue_pen=blue_pen, white_pen=white_pen)

    display.set_pen(label_pen)
    label_width, _ = font.measure_text(_LABEL, _LABEL_SCALE)
    font.draw_text(
        display,
        _LABEL,
        (width - label_width) // 2,
        block_top + _LOGO_SIZE + _LABEL_GAP,
        _LABEL_SCALE,
    )

    if status:
        _draw_status(status)

    os.update_display()


def set_status(os, text):
    """Redraws just the bottom status strip with `text` and flips. No-op if
    show() hasn't run yet (e.g. a stray message before the splash)."""
    if _ctx is None:
        return
    _draw_status(text)
    os.update_display()


def boot_message_handler(os):
    """Returns a handler for os.add_message_handler that mirrors TmOS boot
    messages to the status line. Register it just before os.boot(). It
    stops touching the display once the run loop starts (the dashboard
    owns the screen from then on)."""
    global _boot_messages_active
    _boot_messages_active = True

    def handler(message, severity):
        global _boot_messages_active
        if not _boot_messages_active or severity < MSG_INFO:
            return
        if message == _RUN_LOOP_STARTED_MSG:
            _boot_messages_active = False
            return
        set_status(os, message)

    return handler


def _draw_status(text):
    display = _ctx["display"]
    display.set_pen(_ctx["background_pen"])
    display.rectangle(0, _ctx["status_y"], _ctx["width"], _ctx["status_height"])
    display.set_pen(_ctx["status_pen"])
    text_width, _ = font.measure_text(text, _STATUS_SCALE)
    font.draw_text(
        display, text, (_ctx["width"] - text_width) // 2, _ctx["status_y"], _STATUS_SCALE
    )


def _draw_logo(display, x, y, blue_pen, white_pen):
    """Blits the logo's two color planes at (x, y), scaled by _LOGO_SCALE."""
    _draw_plane(display, BLUE_ROWS, blue_pen, x, y)
    _draw_plane(display, WHITE_ROWS, white_pen, x, y)


def _draw_plane(display, rows, pen, x, y):
    """Blits one color plane, merging contiguous lit columns within each row
    into a single rectangle() call rather than one call per pixel -- the
    same approach dashboard/font.py's _draw_glyph uses for font5x5."""
    display.set_pen(pen)
    for row_index, bits in enumerate(rows):
        col = 0
        while col < _LOGO_NATIVE_SIZE:
            if bits & (1 << (_LOGO_NATIVE_SIZE - 1 - col)):
                start = col
                while col < _LOGO_NATIVE_SIZE and bits & (1 << (_LOGO_NATIVE_SIZE - 1 - col)):
                    col += 1
                display.rectangle(
                    x + start * _LOGO_SCALE,
                    y + row_index * _LOGO_SCALE,
                    (col - start) * _LOGO_SCALE,
                    _LOGO_SCALE,
                )
            else:
                col += 1
