# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Host-only codegen tool -- NOT run on-device, and NOT part of the app.

Flattens an SVG path's curves/arcs into straight-line points, since
picovector.Polygon.path() on the Presto only accepts a flat list of
(x, y) points -- no SVG path syntax, no curves. Used to produce
dashboard/icons.py's HOME_ASSISTANT_OUTLINE from the official
mdi-home-assistant glyph (24x24 viewBox, from
https://github.com/Templarian/MaterialDesign, Apache-2.0).

svgpathtools isn't (and shouldn't become) a project dependency -- it's
only ever needed for this one-off regeneration. Run with:

    uv run --with svgpathtools python scripts/flatten_icon.py

The three small "signal dot" subpaths in the source glyph are exact
circles (verified against their start/end coordinates), so they're
intentionally excluded here and instead drawn at runtime with
Polygon.circle() -- see dashboard/icons.py's HOME_ASSISTANT_DOTS and
dashboard/splash.py.
"""

from svgpathtools import parse_path

# The mdi-home-assistant path `d` attribute, verbatim.
HOME_ASSISTANT_D = (
    "M21.8,13H20V21H13V17.67L15.79,14.88L16.5,15C17.66,15 18.6,14.06 18.6,12.9C18.6,11.74 "
    "17.66,10.8 16.5,10.8A2.1,2.1 0 0,0 14.4,12.9L14.5,13.61L13,15.13V9.65C13.66,9.29 14.1,8.6 "
    "14.1,7.8A2.1,2.1 0 0,0 12,5.7A2.1,2.1 0 0,0 9.9,7.8C9.9,8.6 10.34,9.29 11,9.65V15.13L9.5,"
    "13.61L9.6,12.9A2.1,2.1 0 0,0 7.5,10.8A2.1,2.1 0 0,0 5.4,12.9A2.1,2.1 0 0,0 7.5,15L8.21,"
    "14.88L11,17.67V21H4V13H2.25C1.83,13 1.42,13 1.42,12.79C1.43,12.57 1.85,12.15 2.28,11.72L11,"
    "3C11.33,2.67 11.67,2.33 12,2.33C12.33,2.33 12.67,2.67 13,3L17,7V6H19V9L21.78,11.78C22.18,"
    "12.18 22.59,12.59 22.6,12.8C22.6,13 22.2,13 21.8,13M7.5,12A0.9,0.9 0 0,1 8.4,12.9A0.9,0.9 0 "
    "0,1 7.5,13.8A0.9,0.9 0 0,1 6.6,12.9A0.9,0.9 0 0,1 7.5,12M16.5,12C17,12 17.4,12.4 17.4,12.9C"
    "17.4,13.4 17,13.8 16.5,13.8A0.9,0.9 0 0,1 15.6,12.9A0.9,0.9 0 0,1 16.5,12M12,6.9C12.5,6.9 "
    "12.9,7.3 12.9,7.8C12.9,8.3 12.5,8.7 12,8.7C11.5,8.7 11.1,8.3 11.1,7.8C11.1,7.3 11.5,6.9 12,6.9Z"
)

# How many straight-line segments to approximate each curve/arc with.
CURVE_STEPS = 8


def flatten_outline():
    """Flattens just the housing/antenna outline (the path's first
    subpath) -- the three dot subpaths are exact circles, handled
    separately at runtime instead (see this module's docstring)."""
    subpath = parse_path(HOME_ASSISTANT_D).continuous_subpaths()[0]
    points = []
    for segment in subpath:
        steps = 1 if type(segment).__name__ == "Line" else CURVE_STEPS
        for step in range(1, steps + 1):
            point = segment.point(step / steps)
            points.append((round(float(point.real), 2), round(float(point.imag), 2)))
    # Drop the duplicate closing point (first == last within rounding).
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    return points


if __name__ == "__main__":
    for x, y in flatten_outline():
        print(f"    ({x}, {y}),")
