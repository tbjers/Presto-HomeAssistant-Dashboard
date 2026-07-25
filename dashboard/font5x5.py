# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
5x5-ish pixel font data, hand-drawn in Aseprite by the project owner
(dashboard/assets/font5x5_source.png) -- not derived from compresto or
any other AGPL/MIT source, so no attribution header applies here.

GLYPHS maps an uppercase character to (width, rows): width is that
glyph's own ink width in font units (proportional, not monospace --
see scripts/flatten_font.py's docstring for why), and rows is
CELL_HEIGHT ints, each a `width`-bit mask (bit width-1 = leftmost
column). dashboard/font.py's renderer advances the cursor by
(width + GLYPH_GAP) per character, and by SPACE_WIDTH + GLYPH_GAP
for space or any character with no glyph here (lowercase input is
uppercased first -- this table only defines uppercase letters).

Regenerate with: uv run --with pillow python scripts/flatten_font.py
"""

CELL_HEIGHT = 5
LINE_HEIGHT = 7
GLYPH_GAP = 1
SPACE_WIDTH = 3

GLYPHS = {
    'A': (5, (0b01111, 0b10001, 0b10001, 0b11111, 0b10001)),
    'B': (5, (0b01110, 0b10010, 0b11110, 0b10001, 0b11110)),
    'C': (5, (0b01111, 0b10000, 0b10000, 0b10001, 0b11110)),
    'D': (5, (0b11111, 0b10001, 0b10001, 0b10001, 0b11110)),
    'E': (5, (0b01111, 0b10000, 0b11111, 0b10000, 0b11111)),
    'F': (5, (0b01111, 0b10000, 0b10000, 0b11111, 0b10000)),
    'G': (5, (0b01111, 0b10000, 0b10011, 0b10001, 0b01110)),
    'H': (5, (0b10001, 0b10001, 0b10001, 0b11111, 0b10001)),
    'I': (1, (0b1, 0b1, 0b1, 0b1, 0b1)),
    'J': (5, (0b11111, 0b00001, 0b00001, 0b10001, 0b01110)),
    'K': (5, (0b10001, 0b10010, 0b11110, 0b10001, 0b10001)),
    'L': (5, (0b10000, 0b10000, 0b10000, 0b10000, 0b01111)),
    'M': (5, (0b11110, 0b10101, 0b10101, 0b10101, 0b10101)),
    'N': (5, (0b01111, 0b10001, 0b10001, 0b10001, 0b10001)),
    'O': (5, (0b01111, 0b10001, 0b10001, 0b10001, 0b11110)),
    'P': (5, (0b11111, 0b10001, 0b10001, 0b11110, 0b10000)),
    'Q': (5, (0b01111, 0b10001, 0b10001, 0b11001, 0b11110)),
    'R': (5, (0b01111, 0b10001, 0b10001, 0b11110, 0b10010)),
    'S': (5, (0b01111, 0b10000, 0b01110, 0b00001, 0b11110)),
    'T': (5, (0b11111, 0b00100, 0b00100, 0b00100, 0b00100)),
    'U': (5, (0b10001, 0b10001, 0b10001, 0b10001, 0b01111)),
    'V': (5, (0b10001, 0b10001, 0b10010, 0b10100, 0b01000)),
    'W': (5, (0b10101, 0b10101, 0b10101, 0b10101, 0b01111)),
    'X': (5, (0b10001, 0b10001, 0b01110, 0b10001, 0b10001)),
    'Y': (5, (0b10001, 0b10001, 0b01111, 0b00001, 0b11110)),
    'Z': (5, (0b11111, 0b00001, 0b01110, 0b10000, 0b11111)),
    '0': (5, (0b01111, 0b10001, 0b10101, 0b10001, 0b11110)),
    '1': (2, (0b11, 0b01, 0b01, 0b01, 0b01)),
    '2': (5, (0b11110, 0b00001, 0b01110, 0b10000, 0b11111)),
    '3': (5, (0b11111, 0b00001, 0b11110, 0b00001, 0b11110)),
    '4': (5, (0b10001, 0b10001, 0b10001, 0b01111, 0b00001)),
    '5': (5, (0b11111, 0b10000, 0b11110, 0b00001, 0b11110)),
    '6': (5, (0b01111, 0b10000, 0b11110, 0b10001, 0b11110)),
    '7': (5, (0b11111, 0b10001, 0b00001, 0b00010, 0b00100)),
    '8': (5, (0b01111, 0b10001, 0b01110, 0b10001, 0b11111)),
    '9': (5, (0b01111, 0b10001, 0b01111, 0b00001, 0b01110)),
    '.': (1, (0b0, 0b0, 0b0, 0b0, 0b1)),
    ',': (1, (0b0, 0b0, 0b0, 0b0, 0b1)),
    ';': (1, (0b0, 0b1, 0b0, 0b0, 0b1)),
    ':': (1, (0b0, 0b1, 0b0, 0b0, 0b1)),
    '°': (3, (0b010, 0b101, 0b010, 0b000, 0b000)),
    '%': (5, (0b00000, 0b10001, 0b00010, 0b00100, 0b01000)),
}
