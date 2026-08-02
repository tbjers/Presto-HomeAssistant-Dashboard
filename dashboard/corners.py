# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Pixel-stepped ("blocky"/8-bit-style) rounded-corner rendering, as an
alternative to the smooth antialiased corners PicoVector's
Polygon.rectangle(corners=...) draws (see dashboard/modal.py) -- which
rendering technique to use is CORNER_STYLE_CHOICES' concern
(dashboard/theme.py), not this module's; this module only ever draws the
"blocky" case.

Corner size is expressed in whole `pixel_size`-px blocks (RADIUS_CHOICES:
square/small/medium/large -> 0/1/2/3 blocks), not a continuous radius --
`pixel_size` is meant to be the same "pixel" size dashboard.font5x5's
biggest on-screen text already uses (theme.text_scale(3), the scale
ValueTile/TemperatureTile/DateTimeTile draw their big numbers at -- see
dashboard/theme.py's module docstring), so a rounded corner reads as an
integer number of the same visual "pixels" the rest of the retro-styled
UI is built from, rather than an arbitrary unrelated px count.

corner_notches() builds an exact right-triangle staircase: block (bx, by)
-- 0-indexed grid coordinates, (0, 0) at the corner's sharp tip -- is cut
to background iff bx + by < blocks. E.g. blocks=2:
    XX
    X.
Each row is merged into a single rectangle (row `by` spans columns
0..blocks-1-by), matching dashboard.font's own glyph-blitting convention
of merging contiguous lit runs into one rectangle() call rather than one
per block.
"""

RADIUS_CHOICES = ("square", "small", "medium", "large")
_RADIUS_BLOCKS = {"square": 0, "small": 1, "medium": 2, "large": 3}


def radius_blocks(radius_choice):
    """Block count (0-3) for a RADIUS_CHOICES value; unknown values (e.g.
    a corrupt settings.json -- see dashboard/settings.py) fall back to 0
    ("square"/no rounding), never raise."""
    return _RADIUS_BLOCKS.get(radius_choice, 0)


def corner_notches(pixel_size, blocks):
    """
    Pure geometry, no display access: returns a list of (x, y, w, h)
    background rectangles, in top-left-corner-local pixel coordinates
    (origin at the corner's sharp tip, x growing toward the flat top edge,
    y growing toward the flat left edge), forming a `blocks`-step
    triangular pixel staircase at `pixel_size` px per step.
    """
    if pixel_size <= 0 or blocks <= 0:
        return []

    notches = []
    for by in range(blocks):
        cols = blocks - by
        notches.append((0, by * pixel_size, cols * pixel_size, pixel_size))
    return notches


def draw_blocky_corners(display, x, y, w, h, pixel_size, blocks, erase_pen=None, corner_pens=None):
    """
    Paints notches into all 4 corners of an already-foreground-filled rect
    at (x, y, w, h), approximating rounded corners `blocks` pixel-blocks
    (each `pixel_size` px) deep at each corner.

    Pass exactly one of:
      - `erase_pen`: a single pen applied to all 4 corners -- the common
        case for a standalone shape sitting directly on a flat background.
      - `corner_pens`: a (top_left, top_right, bottom_left, bottom_right)
        4-tuple, for a shape layered on top of another shape whose own
        color shows through differently at different corners (e.g. a
        slider fill drawn over its own track -- see dashboard/modal.py's
        VerticalSliderControl). Kept as a separate parameter, rather than
        overloading `erase_pen`'s type, because a pen handle can itself be
        a tuple (e.g. in tests that fake display.create_pen as returning
        the raw rgb tuple) -- isinstance-sniffing erase_pen would then
        misinterpret a single pen as 4 distinct ones.
    Pen values must already be display.set_pen()-compatible (i.e. from
    dashboard.palette.PenCache, not a raw rgb tuple in production).

    `blocks` is clamped down (never up) to whatever whole-block count fits
    within half of the smaller of `w`/`h` -- deliberately never rounds up
    to exactly reach a dimension's half (unlike an earlier version of this
    function), since forcing that on an odd-sized dimension left a
    1px-tall/wide gap between the top/bottom (or left/right) notch bands
    where the un-notched, still-square corner showed through as a stray
    protruding line (confirmed on real hardware). Simply never attempting
    an exact half-match avoids the whole class of bug -- a slightly smaller
    corner treatment than requested is a much safer failure mode than a
    visible seam.

    No-ops (draws nothing) if the clamped block count is 0 -- callers
    should check corner_style/radius themselves before calling this at all
    (see dashboard/modal.py), since a "square" (0-block) or "smooth"
    corner needs no notches regardless.
    """
    if pixel_size <= 0 or blocks <= 0:
        return

    max_blocks = min(w, h) // (2 * pixel_size)
    blocks = min(blocks, max_blocks)
    notches = corner_notches(pixel_size, blocks)
    if not notches:
        return

    tl_pen, tr_pen, bl_pen, br_pen = corner_pens if corner_pens is not None else (erase_pen,) * 4
    for nx, ny, nw, nh in notches:
        display.set_pen(tl_pen)
        display.rectangle(x + nx, y + ny, nw, nh)
        display.set_pen(tr_pen)
        display.rectangle(x + w - nx - nw, y + ny, nw, nh)
        display.set_pen(bl_pen)
        display.rectangle(x + nx, y + h - ny - nh, nw, nh)
        display.set_pen(br_pen)
        display.rectangle(x + w - nx - nw, y + h - ny - nh, nw, nh)
