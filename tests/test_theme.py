"""
Tests for dashboard.theme.CompressoTheme.
"""

from unittest import mock

from tmos import Region

from dashboard import font5x5, grid, palette
from dashboard.theme import CompressoTheme


def _mock_display():
    display = mock.Mock()
    display.create_pen = mock.Mock(side_effect=lambda *rgb: rgb)  # identity, for asserting later
    display.set_font = mock.Mock()
    display.rectangle = mock.Mock()
    display.line = mock.Mock()
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


def test_base_font_scale_is_left_to_tmos_auto_doubling(mock_presto_module):
    # Unlike padding/systray_height, base_font_scale is NOT pinned -- at our
    # fixed dpi_scale_factor=2, DefaultTheme's base_font_scale=1 auto-doubles
    # to 2, which is exactly right for font5x5's 5-row glyphs to reproduce
    # compresto's measured proportions (see module docstring).
    theme = CompressoTheme()
    theme.setup(_mock_display(), dpi_scale_factor=2)

    assert theme.base_font_scale == 2


def test_text_height_matches_font5x5_glyph_height_at_rel_scale_1(mock_presto_module):
    theme = CompressoTheme()
    theme.setup(_mock_display(), dpi_scale_factor=2)

    assert theme.text_height(rel_scale=1) == font5x5.CELL_HEIGHT * 2  # 10


def test_text_height_scales_with_rel_scale_like_tiles_value_text(mock_presto_module):
    theme = CompressoTheme()
    theme.setup(_mock_display(), dpi_scale_factor=2)

    # ValueTile/DateTimeTile draw their big value text at rel_scale=3.
    assert theme.text_height(rel_scale=3) == font5x5.CELL_HEIGHT * 6  # 30


def test_measure_text_width_is_proportional_ink_width_plus_gap_times_scale(mock_presto_module):
    theme = CompressoTheme()
    theme.setup(_mock_display(), dpi_scale_factor=2)

    width, height = theme.measure_text(_mock_display(), "0709", rel_scale=3)

    expected_units = sum(font5x5.GLYPHS[c][0] + font5x5.GLYPH_GAP for c in "0709")
    assert width == expected_units * 6
    assert height == font5x5.CELL_HEIGHT * 6


def test_measure_text_gives_narrow_glyphs_less_width_than_wide_ones(mock_presto_module):
    # Regression check for the "atrocious kerning" a fixed monospace advance
    # produced: "I" (ink width 1) must measure narrower than "M" (ink width
    # 5), not the same, at the same rel_scale.
    theme = CompressoTheme()
    theme.setup(_mock_display(), dpi_scale_factor=2)

    narrow_width, _ = theme.measure_text(_mock_display(), "I", rel_scale=1)
    wide_width, _ = theme.measure_text(_mock_display(), "M", rel_scale=1)

    assert narrow_width < wide_width


def test_hyphen_em_dash_and_slash_are_mapped_glyphs(mock_presto_module):
    # These were added after the font's first pass (a plain hyphen distinct
    # from the em dash, and a forward slash for e.g. the systray's DD/MM
    # date) -- lock in that they're real glyphs, not blank-but-advancing.
    for char in ("-", "—", "/"):
        assert char in font5x5.GLYPHS


def test_draw_systray_closes_left_and_right_borders(mock_presto_module):
    # Regression check for the systray's left edge reading as an open/
    # "clipped" border: DefaultTheme.draw_systray only draws top/bottom
    # lines, so the leading app-switcher accessory (which has no fill of
    # its own) had no border on its left side at all.
    theme = CompressoTheme()
    display = _mock_display()
    theme.setup(display, dpi_scale_factor=2)

    region = Region(0, 400, 480, 53)
    theme.draw_systray(display, region, adjoined=0)

    left_x = region.x
    right_x = region.x + region.width - 1
    bottom_y = region.y + region.height - 1
    display.line.assert_any_call(left_x, region.y, left_x, bottom_y)
    display.line.assert_any_call(right_x, region.y, right_x, bottom_y)


def test_draw_app_switcher_button_gives_1px_more_left_inset_than_right(mock_presto_module):
    # Regression check for the hamburger icon reading as off-center once
    # draw_systray()'s new left border claimed what used to be pure margin
    # on that side only (measured on real hardware via photo pixel-scan:
    # ~7 device px left vs ~8 right). Fixed by adding 1px more left inset
    # than right -- verify bar x/width reflect that asymmetric inset rather
    # than DefaultTheme's originally-symmetric one.
    theme = CompressoTheme()
    display = _mock_display()
    theme.setup(display, dpi_scale_factor=2)

    region = Region(0, 400, 53, 53)
    theme.draw_app_switcher_button(display, region, is_pressed=False)

    spacing = 3 * theme.dpi_scale_factor
    expected_x = region.x + spacing + 1
    expected_width = region.width - (spacing + 1) - spacing
    for call in display.rectangle.call_args_list:
        x, _, width, _ = call.args
        assert x == expected_x
        assert width == expected_width


def test_text_draws_rectangles_for_a_known_glyph(mock_presto_module):
    theme = CompressoTheme()
    display = _mock_display()
    theme.setup(display, dpi_scale_factor=2)

    theme.text(display, "I", 10, 20, rel_scale=1)

    # font5x5's "I" is a single lit column per row (CELL_HEIGHT rows) -- one
    # merged rectangle() call per row, none empty.
    assert display.rectangle.call_count == font5x5.CELL_HEIGHT


def test_text_lowercases_are_uppercased_and_unmapped_chars_still_advance(mock_presto_module):
    theme = CompressoTheme()
    display = _mock_display()
    theme.setup(display, dpi_scale_factor=2)

    # lowercase "i" should render the same as "I" (one rect per row), and the
    # trailing "@" (not in font5x5.GLYPHS) should be skipped without error.
    assert "@" not in font5x5.GLYPHS
    theme.text(display, "i@", 0, 0, rel_scale=1)

    assert display.rectangle.call_count == font5x5.CELL_HEIGHT
