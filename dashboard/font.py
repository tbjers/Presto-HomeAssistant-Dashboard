# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Renderer for dashboard.font5x5's glyph data -- draws text directly via
display.rectangle() instead of going through PicoGraphics' own font/set_font
machinery, since font5x5 isn't a format PicoGraphics knows how to load.

Split out from dashboard.theme (which adapts this to Theme's rel_scale/
text_scale semantics for tiles.py et al) so dashboard.splash -- which runs
before OS.boot() and doesn't have a Theme instance to work with -- can use
the same font directly at an explicit integer pixel scale.

font5x5 is a proportional font: each glyph has its own ink width, and the
cursor advances by (glyph width + GLYPH_GAP) per character -- an earlier,
monospace version (fixed advance = the source sheet's authoring cell width)
faithfully reproduced the source art, but that art centers narrow glyphs
(I, 1, punctuation) in their cell while wide ones sit flush against its
right edge, so a fixed advance put uneven, oversized gaps around every
narrow character. Lowercase input is folded to uppercase (the font only
defines uppercase letters); characters with no glyph (space, lowercase-only
symbols, accented letters) advance by SPACE_WIDTH + GLYPH_GAP but draw
nothing, so callers don't need to pre-sanitize strings or worry about width
becoming unpredictable.
"""

from dashboard import font5x5


def measure_text(text, scale):
    """Returns (width, height) in pixels for `text` drawn at `scale`."""
    width = 0
    for char in text.upper():
        glyph = font5x5.GLYPHS.get(char)
        glyph_width = glyph[0] if glyph else font5x5.SPACE_WIDTH
        width += (glyph_width + font5x5.GLYPH_GAP) * scale
    return width, font5x5.CELL_HEIGHT * scale


def draw_text(display, text, x, y, scale):
    """Draws `text` with its top-left corner at (x, y), at `scale` pixels
    per font unit. Uses whatever pen is currently set on `display`."""
    cursor_x = x
    for char in text.upper():
        glyph = font5x5.GLYPHS.get(char)
        if glyph:
            width, rows = glyph
            _draw_glyph(display, rows, width, cursor_x, y, scale)
        else:
            width = font5x5.SPACE_WIDTH
        cursor_x += (width + font5x5.GLYPH_GAP) * scale


def _draw_glyph(display, rows, width, x, y, scale):
    """Blits one glyph, merging contiguous lit columns within each row into
    a single rectangle() call rather than one call per pixel."""
    for row_index, bits in enumerate(rows):
        col = 0
        while col < width:
            if bits & (1 << (width - 1 - col)):
                start = col
                while col < width and bits & (1 << (width - 1 - col)):
                    col += 1
                display.rectangle(
                    x + start * scale, y + row_index * scale, (col - start) * scale, scale
                )
            else:
                col += 1
