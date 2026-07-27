# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Renders dashboard.weather_icons' flattened MDI weather glyphs -- the same
approach dashboard.splash uses for the Home Assistant glyph: each
condition's flattened subpaths are scaled from their 24x24 viewBox to a
target on-screen size and drawn as one or more Polygon.path() calls under a
single pen color (monochrome).

Kept separate from dashboard.splash (which runs before OS.boot() and draws
directly to os.display with no Theme available yet) since WeatherTile draws
through the normal Page/Theme machinery instead.

dashboard.weather_icons stores each icon as (lengths, data) -- a packed
bytes blob of fixed-point coordinates, not plain (x, y) tuples -- see that
module's docstring for why (32s import time on real hardware otherwise).
array.array("H", data) decodes it back into flat little-endian uint16s at
draw time; this only runs when a tile's condition actually changes
(dirty-tracked, see dashboard/page.py), so the decode cost here is
negligible compared to the import-time cost it avoids.
"""

from array import array

from picovector import ANTIALIAS_BEST, PicoVector, Polygon, Transform

from dashboard.weather_icons import FIXED_POINT_SCALE, VIEWBOX, WEATHER_ICONS

_FALLBACK_CONDITION = "cloudy"


def draw(display, condition, x, y, size, pen):
    """
    Draws the icon for `condition` at (x, y), scaled to `size` pixels
    square, under `pen`. Falls back to a generic cloud glyph for an
    unrecognized or None condition -- never raises.
    """
    lengths, data = WEATHER_ICONS.get(condition, WEATHER_ICONS[_FALLBACK_CONDITION])
    scale = size / VIEWBOX / FIXED_POINT_SCALE
    coords = array("H", data)

    vector = PicoVector(display)
    vector.set_antialiasing(ANTIALIAS_BEST)
    vector.set_transform(Transform())

    icon = Polygon()
    offset = 0
    for length in lengths:
        points = []
        for i in range(length):
            px = coords[offset + i * 2]
            py = coords[offset + i * 2 + 1]
            points.append((x + px * scale, y + py * scale))
        offset += length * 2
        icon.path(*points)

    display.set_pen(pen)
    vector.draw(icon)
