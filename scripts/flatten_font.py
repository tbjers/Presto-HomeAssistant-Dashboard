# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Host-only codegen tool -- NOT run on-device, and NOT part of the app.

Flattens dashboard/assets/font5x5_source.png (a hand-drawn pixel font
authored in Aseprite by the project owner) into dashboard/font5x5.py's
GLYPHS table.

The source sheet lays every glyph out on a uniform CELL_WIDTH x CELL_HEIGHT
authoring grid (row 1: A-Z, row 2: 0-9 then . , ; : degree %), but glyphs are
NOT all the same ink width within that grid -- most letters/digits fill
columns 2-6 (5px wide, flush against the cell's right edge), while I/1/./,/;
/: are 1-2px wide and centered in the cell instead. A first version blitted
the whole 7px cell verbatim and advanced by a fixed 7px every character
(monospace); that faithfully reproduced the source art's per-glyph padding,
but the padding itself is inconsistent (flush-right for wide glyphs,
centered for narrow ones), so real text came out with uneven, "atrocious"
looking gaps around every I/1/punctuation. Fixed by tight-cropping each
glyph to its actual ink bounding box and switching to proportional
per-glyph advance (ink width + GLYPH_GAP) in dashboard/font.py -- see this
script's pixel-scan in git history for the measured per-glyph widths that
motivated this.

Not a dependency for the app itself -- only needed to regenerate the font
table. Run with:

    uv run --with pillow python scripts/flatten_font.py
"""

from pathlib import Path

from PIL import Image

SOURCE = Path(__file__).parent.parent / "dashboard" / "assets" / "font5x5_source.png"
OUTPUT = Path(__file__).parent.parent / "dashboard" / "font5x5.py"

# The authoring grid in the source sheet -- NOT the final glyph width (see
# module docstring). Only used to locate each glyph's cell before cropping.
CELL_WIDTH = 7
CELL_HEIGHT = 5

# Row pitch in the source sheet (row 2 starts at y=8, row 1 at y=1) --
# reused as-is for dashboard.font5x5.LINE_HEIGHT, the vertical line pitch
# for multi-line text.
LINE_HEIGHT = 7

# Gap between glyphs, and the advance width for space/unmapped characters --
# both in font units (pre-scale). Chosen to look right at the two sizes
# used on real hardware so far (tiles.py's rel_scale 1 and 3), not derived
# from the source image -- there's no "space" glyph to measure.
GLYPH_GAP = 1
SPACE_WIDTH = 3

# (row_y_offset, characters_left_to_right) for each row of glyphs in the sheet.
ROWS = [
    (1, "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    (8, "0123456789.,;:°%-—/"),
]


def _is_ink(pixel):
    # Source is LA (luminance + alpha); glyphs are opaque black on
    # transparent, so alpha is the shape channel, not luminance.
    return pixel[-1] > 128


def _tight_crop(pixels, cell_x, row_y):
    """Returns (width, rows) for the glyph at (cell_x, row_y), cropped to
    its actual ink columns rather than the full CELL_WIDTH authoring cell."""
    lit_columns = [
        dx
        for dx in range(CELL_WIDTH)
        if any(_is_ink(pixels[cell_x + dx, row_y + dy]) for dy in range(CELL_HEIGHT))
    ]
    left, right = min(lit_columns), max(lit_columns)
    width = right - left + 1
    rows = []
    for dy in range(CELL_HEIGHT):
        bits = 0
        for dx in range(left, right + 1):
            bits <<= 1
            if _is_ink(pixels[cell_x + dx, row_y + dy]):
                bits |= 1
        rows.append(bits)
    return width, tuple(rows)


def extract_glyphs():
    image = Image.open(SOURCE).convert("LA")
    pixels = image.load()
    glyphs = {}
    for row_y, chars in ROWS:
        for col, char in enumerate(chars):
            glyphs[char] = _tight_crop(pixels, col * CELL_WIDTH, row_y)
    return glyphs


def render(glyphs):
    lines = [
        '# SPDX-License-Identifier: AGPL-3.0-or-later',
        '# Copyright (C) 2026  Torgny Bjers',
        '',
        '"""',
        "5x5-ish pixel font data, hand-drawn in Aseprite by the project owner",
        "(dashboard/assets/font5x5_source.png) -- not derived from compresto or",
        "any other AGPL/MIT source, so no attribution header applies here.",
        "",
        "GLYPHS maps an uppercase character to (width, rows): width is that",
        "glyph's own ink width in font units (proportional, not monospace --",
        "see scripts/flatten_font.py's docstring for why), and rows is",
        "CELL_HEIGHT ints, each a `width`-bit mask (bit width-1 = leftmost",
        "column). dashboard/font.py's renderer advances the cursor by",
        "(width + GLYPH_GAP) per character, and by SPACE_WIDTH + GLYPH_GAP",
        "for space or any character with no glyph here (lowercase input is",
        "uppercased first -- this table only defines uppercase letters).",
        "",
        "Regenerate with: uv run --with pillow python scripts/flatten_font.py",
        '"""',
        '',
        f"CELL_HEIGHT = {CELL_HEIGHT}",
        f"LINE_HEIGHT = {LINE_HEIGHT}",
        f"GLYPH_GAP = {GLYPH_GAP}",
        f"SPACE_WIDTH = {SPACE_WIDTH}",
        '',
        "GLYPHS = {",
    ]
    for char, (width, rows) in glyphs.items():
        key = repr(char)
        rows_str = ", ".join(f"0b{bits:0{width}b}" for bits in rows)
        lines.append(f"    {key}: ({width}, ({rows_str})),")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    glyphs = extract_glyphs()
    OUTPUT.write_text(render(glyphs), encoding="utf-8")
    print(f"Wrote {len(glyphs)} glyphs to {OUTPUT}")
