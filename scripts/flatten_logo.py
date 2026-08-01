# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Host-only codegen tool -- NOT run on-device, and NOT part of the app.

Flattens dashboard/assets/logo.png (a hand-drawn 32x32 pixel logotype
authored in Aseprite by the project owner, sources/home-assistant-logo.aseprite)
into dashboard/logo.py's row-bitmask tables, the same "pack ink into bitmasks
and blit contiguous runs as rectangles" approach scripts/flatten_font.py uses
for font5x5 -- there's no PicoGraphics-native way to load a PNG on-device, and
at only 32x32x2 planes (64 int literals total) this is nowhere near the
literal-count MicroPython compiler blowup that motivated weather_icons.py's
packed-bytes+array format (see that module's docstring).

The source image is a flat-color P-mode PNG with exactly 3 colors: fully
transparent background, opaque brand blue, and opaque white -- verified by
inspection, not assumed. Each ink color becomes its own 32-row bitmask plane
(one 32-bit mask per row, bit 31 = leftmost column), drawn as two separate
blits (blue then white) so overlapping-color anti-aliasing is a non-issue.

Not a dependency for the app itself -- only needed to regenerate the logo
table. Run with:

    uv run --with pillow python scripts/flatten_logo.py
"""

from pathlib import Path

from PIL import Image

SOURCE = Path(__file__).parent.parent / "dashboard" / "assets" / "logo.png"
OUTPUT = Path(__file__).parent.parent / "dashboard" / "logo.py"

WHITE = (255, 255, 255)


def extract_planes():
    image = Image.open(SOURCE).convert("RGBA")
    pixels = image.load()
    width, height = image.size

    blue = None
    blue_rows = []
    white_rows = []
    for y in range(height):
        blue_bits = 0
        white_bits = 0
        for x in range(width):
            r, g, b, a = pixels[x, y]
            blue_bits <<= 1
            white_bits <<= 1
            if a < 128:
                continue
            if (r, g, b) == WHITE:
                white_bits |= 1
            else:
                blue_bits |= 1
                if blue is None:
                    blue = (r, g, b)
        blue_rows.append(blue_bits)
        white_rows.append(white_bits)
    return width, height, blue, tuple(blue_rows), tuple(white_rows)


def render(width, height, blue, blue_rows, white_rows):
    lines = [
        '# SPDX-License-Identifier: AGPL-3.0-or-later',
        '# Copyright (C) 2026  Torgny Bjers',
        '',
        '"""',
        "Home Assistant logotype pixel data, flattened from",
        "dashboard/assets/logo.png (hand-drawn in Aseprite by the project",
        "owner, sources/home-assistant-logo.aseprite) -- not derived from",
        "compresto or any other AGPL/MIT source, so no attribution header",
        "applies here.",
        "",
        "WIDTH/HEIGHT are the source image's native pixel dimensions. BLUE_ROWS",
        "and WHITE_ROWS are each HEIGHT ints, one per row, a WIDTH-bit mask",
        "(bit WIDTH-1 = leftmost column) marking which pixels in that row are",
        "ink of that color -- transparent background pixels set no bit in",
        "either plane. dashboard/logo.py's renderer blits each plane as",
        "merged-run rectangles, the same approach dashboard/font.py uses for",
        "font5x5 glyphs.",
        "",
        "Regenerate with: uv run --with pillow python scripts/flatten_logo.py",
        '"""',
        '',
        f"WIDTH = {width}",
        f"HEIGHT = {height}",
        f"BLUE = {blue!r}",
        '',
        "BLUE_ROWS = (",
    ]
    for bits in blue_rows:
        lines.append(f"    0b{bits:0{width}b},")
    lines.append(")")
    lines.append('')
    lines.append("WHITE_ROWS = (")
    for bits in white_rows:
        lines.append(f"    0b{bits:0{width}b},")
    lines.append(")")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    width, height, blue, blue_rows, white_rows = extract_planes()
    OUTPUT.write_text(render(width, height, blue, blue_rows, white_rows), encoding="utf-8")
    print(f"Wrote {width}x{height} logo ({blue} ink) to {OUTPUT}")
