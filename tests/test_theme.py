"""
Tests for dashboard.theme.CompressoTheme.
"""

from unittest import mock

from dashboard import grid, palette
from dashboard.theme import CompressoTheme


def _mock_display():
    display = mock.Mock()
    display.create_pen = mock.Mock(side_effect=lambda *rgb: rgb)  # identity, for asserting later
    display.set_font = mock.Mock()
    return display


def test_pens_are_converted_from_compresto_rgb_tuples(mock_presto_module):
    theme = CompressoTheme()
    display = _mock_display()

    theme.setup(display, dpi_scale_factor=2)

    display.create_pen.assert_any_call(*palette.GRAY_950)
    display.create_pen.assert_any_call(*palette.GRAY_200)
    display.create_pen.assert_any_call(*palette.GRAY_900)
    display.create_pen.assert_any_call(*palette.ROSE_600)
    assert theme.background_pen == palette.GRAY_950
    assert theme.foreground_pen == palette.GRAY_200
    assert theme.secondary_background_pen == palette.GRAY_900
    assert theme.error_pen == palette.ROSE_600


def test_padding_is_pinned_to_grid_gap_not_doubled_by_dpi_scaling(mock_presto_module):
    theme = CompressoTheme()
    theme.setup(_mock_display(), dpi_scale_factor=2)

    assert theme.padding == grid.GAP  # 8, not 16


def test_systray_height_is_pinned_to_two_grid_rows(mock_presto_module):
    theme = CompressoTheme()
    theme.setup(_mock_display(), dpi_scale_factor=2)

    expected = round(grid.span_size(grid.tile_size(480), 2))
    assert theme.systray_height == expected == 53


def test_padding_and_systray_height_are_pinned_regardless_of_dpi_scale_factor(mock_presto_module):
    # Even if dpi_scale_factor were 1 (full_res=False), our overrides should
    # still win over Theme's automatic scaling — pinning to explicit final
    # values, not reference values, is deliberate (see module docstring).
    theme = CompressoTheme()
    theme.setup(_mock_display(), dpi_scale_factor=1)

    assert theme.padding == grid.GAP
    assert theme.systray_height == 53
