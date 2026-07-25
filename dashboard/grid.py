# Layout math and constants adapted from compresto
# (https://git.hack-hro.de/kmohrf/compresto), Copyright (C) Konrad Mohrfeldt,
# licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the "Licensing" section of CLAUDE.md.

"""
Tile-grid math, ported from compresto's WIDTH/GAP/TILE_SIZE/size() layout,
generalized to operate on a TmOS Region instead of a hardcoded screen size so
it stays correct if the page is ever given a sub-screen region (e.g. the
systray shrinking the content region).

The base grid is deliberately finer than compresto's original 4 columns: a
16-column base grid lets the systray occupy a slim, properly grid-aligned
strip (1-2 base rows) instead of being forced to be at least one full
tile-sized cell tall. Standard "visual" tiles span STANDARD_SPAN x
STANDARD_SPAN base cells, which reproduces the same 114px tile size compresto
used at a 4-column grid (22.5 * 4 + 8 * 3 = 114) — this is a finer
subdivision of the same visual layout, not a different one.
"""

from tmos import Region

COLUMNS = 16
GAP = 8

# Cells-per-edge for a "standard" visual tile (what used to be a plain 1x1
# tile back when COLUMNS was 4). Config/tiles code should use this rather
# than hardcoding 4.
STANDARD_SPAN = 4


def tile_size(region_width: int) -> float:
    """Edge length of one square grid cell for a region this wide."""
    return (region_width - (GAP * (COLUMNS - 1))) / COLUMNS


def span_size(tile: float, cells: int) -> float:
    """Cumulative size for a tile spanning `cells` grid cells (compresto's size())."""
    return (tile * cells) + (GAP * (cells - 1))


def cell_region(region: Region, col: int, row: int, colspan: int = 1, rowspan: int = 1) -> Region:
    """
    Region for a tile at (col, row) spanning colspan x rowspan cells within
    `region`, in the same coordinate space as `region` (absolute/screen space
    if `region` is, region-relative if it isn't).
    """
    tile = tile_size(region.width)
    x = region.x + col * (tile + GAP)
    y = region.y + row * (tile + GAP)
    width = span_size(tile, colspan)
    height = span_size(tile, rowspan)
    return Region(int(round(x)), int(round(y)), int(round(width)), int(round(height)))
