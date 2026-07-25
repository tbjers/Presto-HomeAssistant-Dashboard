# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Icon path data for on-device vector rendering.

picovector.Polygon.path() on this device only accepts a flat list of
straight-line (x, y) points -- unlike browser/desktop SVG renderers, it does
not parse SVG path syntax and cannot draw curves directly. HOME_ASSISTANT_OUTLINE
below was produced by flattening the curved/arc segments of the official
mdi-home-assistant glyph (24x24 viewBox, from
https://github.com/Templarian/MaterialDesign, Apache-2.0) into straight
edges with svgpathtools -- see scripts/flatten_icon.py to regenerate.

Coordinates are in the icon's original 24x24 viewBox space; callers
scale/translate them to screen pixels at draw time (see dashboard/splash.py).
"""

# The house/antenna outline -- straight edges plus small fillet arcs, so it
# needs the point-by-point flattening scripts/flatten_icon.py does.
HOME_ASSISTANT_OUTLINE = [
    (20.0, 13.0), (20.0, 21.0), (13.0, 21.0), (13.0, 17.67), (15.79, 14.88),
    (16.5, 15.0), (16.92, 14.96), (17.32, 14.84), (17.67, 14.64), (17.98, 14.39),
    (18.24, 14.07), (18.44, 13.72), (18.56, 13.32), (18.6, 12.9), (18.56, 12.48),
    (18.44, 12.08), (18.24, 11.73), (17.99, 11.42), (17.67, 11.16), (17.32, 10.97),
    (16.92, 10.84), (16.5, 10.8), (16.09, 10.84), (15.7, 10.96), (15.33, 11.15),
    (15.02, 11.42), (14.75, 11.73), (14.56, 12.1), (14.44, 12.49), (14.4, 12.9),
    (14.5, 13.61), (13.0, 15.13), (13.0, 9.65), (13.24, 9.5), (13.45, 9.32),
    (13.64, 9.12), (13.8, 8.89), (13.93, 8.64), (14.02, 8.38), (14.08, 8.09),
    (14.1, 7.8), (14.06, 7.39), (13.94, 7.0), (13.75, 6.63), (13.48, 6.32),
    (13.17, 6.05), (12.8, 5.86), (12.41, 5.74), (12.0, 5.7), (11.59, 5.74),
    (11.2, 5.86), (10.83, 6.05), (10.52, 6.32), (10.25, 6.63), (10.06, 7.0),
    (9.94, 7.39), (9.9, 7.8), (9.92, 8.09), (9.98, 8.38), (10.07, 8.64),
    (10.2, 8.89), (10.36, 9.12), (10.55, 9.32), (10.76, 9.5), (11.0, 9.65),
    (11.0, 15.13), (9.5, 13.61), (9.6, 12.9), (9.56, 12.49), (9.44, 12.1),
    (9.25, 11.73), (8.98, 11.42), (8.67, 11.15), (8.3, 10.96), (7.91, 10.84),
    (7.5, 10.8), (7.09, 10.84), (6.7, 10.96), (6.33, 11.15), (6.02, 11.42),
    (5.75, 11.73), (5.56, 12.1), (5.44, 12.49), (5.4, 12.9), (5.44, 13.31),
    (5.56, 13.7), (5.75, 14.07), (6.02, 14.38), (6.33, 14.65), (6.7, 14.84),
    (7.09, 14.96), (7.5, 15.0), (8.21, 14.88), (11.0, 17.67), (11.0, 21.0),
    (4.0, 21.0), (4.0, 13.0), (2.25, 13.0), (2.09, 13.0), (1.94, 13.0),
    (1.8, 12.99), (1.68, 12.97), (1.57, 12.95), (1.49, 12.91), (1.44, 12.86),
    (1.42, 12.79), (1.44, 12.7), (1.5, 12.59), (1.58, 12.47), (1.69, 12.33),
    (1.82, 12.19), (1.97, 12.04), (2.12, 11.88), (2.28, 11.72), (11.0, 3.0),
    (11.12, 2.88), (11.25, 2.76), (11.37, 2.64), (11.5, 2.54), (11.63, 2.45),
    (11.75, 2.39), (11.88, 2.35), (12.0, 2.33), (12.12, 2.35), (12.25, 2.39),
    (12.37, 2.45), (12.5, 2.54), (12.63, 2.64), (12.75, 2.76), (12.88, 2.88),
    (13.0, 3.0), (17.0, 7.0), (17.0, 6.0), (19.0, 6.0), (19.0, 9.0),
    (21.78, 11.78), (21.93, 11.93), (22.08, 12.08), (22.21, 12.22), (22.34, 12.36),
    (22.44, 12.49), (22.52, 12.61), (22.58, 12.71), (22.6, 12.8), (22.58, 12.87),
    (22.53, 12.92), (22.45, 12.95), (22.35, 12.98), (22.23, 12.99), (22.09, 13.0),
    (21.95, 13.0), (21.8, 13.0),
]

# (center_x, center_y, radius) -- the three "signal" dots. Confirmed to be
# exact circles against the source path's endpoints, so these are drawn at
# runtime with Polygon.circle() rather than needing flattened points.
HOME_ASSISTANT_DOTS = [
    (7.5, 12.9, 0.9),
    (16.5, 12.9, 0.9),
    (12.0, 7.8, 0.9),
]

# The viewBox the coordinates above are expressed in.
HOME_ASSISTANT_VIEWBOX = 24
