"""
Tests for dashboard.grid tile-layout math.
"""

from tmos import Region

from dashboard.grid import GAP, COLUMNS, STANDARD_SPAN, tile_size, span_size, cell_region


def test_tile_size_matches_presto_screen_width():
    # (480 - 8*15) / 16 = 22.5
    assert tile_size(480) == 22.5


def test_span_size_single_cell_equals_tile_size():
    assert span_size(22.5, 1) == 22.5


def test_span_size_standard_span_reproduces_original_114px_tile():
    # A STANDARD_SPAN x STANDARD_SPAN tile must equal compresto's original
    # 4-column 114px tile size — this 16-column grid is a finer subdivision
    # of the same visual layout, not a different one.
    assert span_size(tile_size(480), STANDARD_SPAN) == 114.0


def test_cell_region_top_left_standard_tile_is_flush_with_region_origin():
    region = Region(0, 0, 480, 480)
    cell = cell_region(region, col=0, row=0, colspan=STANDARD_SPAN, rowspan=STANDARD_SPAN)
    assert cell == Region(0, 0, 114, 114)


def test_cell_region_standard_tiles_are_spaced_by_gap():
    region = Region(0, 0, 480, 480)
    first = cell_region(region, col=0, row=0, colspan=STANDARD_SPAN, rowspan=STANDARD_SPAN)
    second = cell_region(region, col=STANDARD_SPAN, row=0, colspan=STANDARD_SPAN, rowspan=STANDARD_SPAN)
    assert second.x - (first.x + first.width) == GAP


def test_cell_region_four_standard_tiles_span_full_480_width():
    region = Region(0, 0, 480, 480)
    last = cell_region(
        region, col=COLUMNS - STANDARD_SPAN, row=0, colspan=STANDARD_SPAN, rowspan=STANDARD_SPAN
    )
    assert last.x + last.width == region.x + region.width


def test_cell_region_rows_are_spaced_by_gap_between_standard_tiles():
    region = Region(0, 0, 480, 480)
    first = cell_region(region, col=0, row=0, colspan=STANDARD_SPAN, rowspan=STANDARD_SPAN)
    second = cell_region(region, col=0, row=STANDARD_SPAN, colspan=STANDARD_SPAN, rowspan=STANDARD_SPAN)
    assert second.y - (first.y + first.height) == GAP


def test_cell_region_respects_nonzero_region_origin():
    # Simulates a page region offset by a grid-aligned systray (2 base rows
    # tall: 22.5*2 + 8*1 = 53).
    region = Region(0, 53, 480, 427)
    cell = cell_region(region, col=0, row=0, colspan=STANDARD_SPAN, rowspan=STANDARD_SPAN)
    assert cell.x == 0
    assert cell.y == 53


def test_single_base_cell_is_much_smaller_than_a_standard_tile():
    # Documents *why* 16 columns: a lone base cell (22.5px) is small enough
    # to serve as a slim systray row, unlike the old 4-column grid where the
    # smallest addressable unit was already a full 114px tile.
    tile = tile_size(480)
    assert tile < 30  # comfortably under TmOS DefaultTheme's default systray_height
