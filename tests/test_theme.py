"""
Tests for dashboard.theme.CompressoTheme.
"""

from unittest import mock

import picovector
import pytest

from tmos import Region

from dashboard import corners, font5x5, grid, palette
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
    display.create_pen.assert_any_call(*palette.ROSE_600)
    assert theme.background_pen == palette.GRAY_950
    assert theme.foreground_pen == palette.GRAY_200
    assert theme.secondary_background_pen == palette.GRAY_950
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


def test_draw_systray_closes_all_four_borders_as_1px_rectangles(mock_presto_module):
    # Regression check, two incidents:
    # 1. The systray's left edge read as an open/"clipped" border --
    #    DefaultTheme.draw_systray (tmos_ui.py) only draws top/bottom
    #    lines, so the leading app-switcher accessory (which has no fill
    #    of its own) had no border on its left side at all.
    # 2. Those top/bottom borders, drawn via display.line(), rendered
    #    visibly thicker on real hardware than the 1px display.rectangle()
    #    outline draw_button_frame/draw_app_switcher_button use --
    #    confirmed on-device right where the hamburger button's own
    #    outline sits flush against the systray's bottom border. All four
    #    sides are drawn as explicit 1px rectangles now, not lines.
    theme = CompressoTheme()
    display = _mock_display()
    theme.setup(display, dpi_scale_factor=2)

    region = Region(0, 400, 480, 53)
    theme.draw_systray(display, region, adjoined=0)

    x, y, w, h = region
    display.line.assert_not_called()
    display.rectangle.assert_any_call(x, y, w, 1)  # top
    display.rectangle.assert_any_call(x, y + h - 1, w, 1)  # bottom
    display.rectangle.assert_any_call(x, y, 1, h)  # left
    display.rectangle.assert_any_call(x + w - 1, y, 1, h)  # right


def test_draw_systray_page_button_frame_leaves_a_gap_above_the_border(mock_presto_module):
    # Regression check: this region shares the systray's own y/height, so
    # its bottom row is the exact same row draw_systray() draws its 1px
    # border on. An underline flush against that row merged into it,
    # reading as the systray border doubling in thickness specifically
    # under the current page's tab -- confirmed on real hardware. The
    # underline must land above a gap, not touching the border row.
    theme = CompressoTheme()
    display = _mock_display()
    theme.setup(display, dpi_scale_factor=2)

    region = Region(50, 400, 100, 53)
    theme.draw_systray_page_button_frame(display, region, is_pressed=True, adjoined=0)

    x, y, w, h = region
    border_row = y + h - 1
    gap = 2
    underline_height = 2
    display.rectangle.assert_called_once_with(
        x, border_row - gap - underline_height, w, underline_height
    )


def test_draw_systray_page_button_frame_draws_nothing_when_not_current(mock_presto_module):
    theme = CompressoTheme()
    display = _mock_display()
    theme.setup(display, dpi_scale_factor=2)
    display.rectangle.reset_mock()

    region = Region(50, 400, 100, 53)
    theme.draw_systray_page_button_frame(display, region, is_pressed=False, adjoined=0)

    display.rectangle.assert_not_called()


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
    # First two calls are the button's outline (full rect + inset rect);
    # the remaining three are the hamburger bars themselves.
    for call in display.rectangle.call_args_list[2:]:
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


def _reset_vector_mocks():
    # Theme._vector (tmos_ui.py) is a class attribute shared across every
    # Theme instance/test in the session -- reset the mock's recorded calls
    # so assertions here don't pick up state from other tests (same idiom
    # as tests/test_modal.py's own _reset_vector_mocks()).
    picovector.PicoVector.reset_mock()
    picovector.PicoVector.return_value.reset_mock()
    picovector.PicoVector.return_value.measure_text.return_value = (0, 0, 50, 20)


class TestCornerDefaults:
    def test_default_style_is_smooth(self):
        assert CompressoTheme.corner_style == "smooth"

    def test_default_radius_is_a_known_choice(self):
        assert CompressoTheme.corner_radius in corners.RADIUS_CHOICES


class TestFontChoiceSetup:
    def test_default_font_choice_keeps_bitmap8_and_font5x5_metrics(self, mock_presto_module):
        theme = CompressoTheme()
        theme.setup(_mock_display(), dpi_scale_factor=2)

        assert theme.font == "bitmap8"
        assert theme.base_text_height == font5x5.CELL_HEIGHT * theme.base_font_scale

    # Atkinson/Inter are temporarily removed from FONT_CHOICES (see
    # dashboard/theme.py's FONT_CHOICES comment -- loading a PicoVector
    # .af font hung real hardware), so setting theme.font_choice to either
    # string no longer resolves to a path at all -- these tests are
    # skipped rather than rewritten to fake the vector path, since there's
    # nothing meaningful left to exercise until the gate is lifted (undo
    # by restoring the FONT_CHOICES entries; no test changes needed).
    @pytest.mark.skip(reason="Atkinson/Inter gated off -- FONT_CHOICES has only 'default' right now")
    @pytest.mark.parametrize("choice", ["atkinson", "inter"])
    def test_vector_font_choice_sets_font_path_and_pixel_size(self, mock_presto_module, choice):
        _reset_vector_mocks()
        theme = CompressoTheme()
        theme.font_choice = choice
        display = _mock_display()

        theme.setup(display, dpi_scale_factor=2)

        assert theme.font == CompressoTheme.FONT_CHOICES[choice]
        # base_font_scale is a *pixel font size* for PicoVector (VECTOR_
        # FONT_SIZE), not font5x5's dpi-scaled multiplier -- see
        # dashboard/theme.py's module docstring for why reusing that
        # multiplier would render the font unreadably small.
        assert theme.base_font_scale == CompressoTheme.VECTOR_FONT_SIZE
        vector = picovector.PicoVector.return_value
        # Regression check: Theme.setup() (tmos_ui.py) makes its own
        # internal set_font() call using whatever base_font_scale holds at
        # that point, before CompressoTheme's own
        # _configure_font_metrics() gets a chance to set it -- checking
        # only the *last* call (assert_called_with) let a real bug through
        # where that first, internal call used size 1 (DefaultTheme's
        # bitmap-scale default) instead of VECTOR_FONT_SIZE, which hung
        # real hardware. Every call must use the right size, not just the
        # final one.
        assert vector.set_font.call_count >= 1
        for call in vector.set_font.call_args_list:
            assert call.args == (theme.font, CompressoTheme.VECTOR_FONT_SIZE)

    @pytest.mark.skip(reason="Atkinson/Inter gated off -- FONT_CHOICES has only 'default' right now")
    def test_vector_font_choice_uses_vector_tuned_metrics_not_font5x5s(self, mock_presto_module):
        _reset_vector_mocks()
        theme = CompressoTheme()
        theme.font_choice = "inter"

        theme.setup(_mock_display(), dpi_scale_factor=2)

        assert theme.base_text_height == round(
            CompressoTheme.VECTOR_FONT_SIZE * CompressoTheme.VECTOR_FONT_CAP_HEIGHT_RATIO
        )
        assert theme.base_line_height == round(
            CompressoTheme.VECTOR_FONT_SIZE * CompressoTheme.VECTOR_FONT_LINE_HEIGHT_RATIO
        )
        # Explicitly NOT font5x5's 5-row metrics -- those are only correct
        # for the bitmap-multiplier regime.
        assert theme.base_text_height != font5x5.CELL_HEIGHT * theme.base_font_scale


class TestTextDispatch:
    def test_default_choice_uses_font_module(self, mock_presto_module):
        theme = CompressoTheme()
        display = _mock_display()
        theme.setup(display, dpi_scale_factor=2)

        theme.text(display, "I", 10, 20, rel_scale=1)

        assert display.rectangle.call_count == font5x5.CELL_HEIGHT  # font.draw_text path

    @pytest.mark.skip(reason="Atkinson/Inter gated off -- FONT_CHOICES has only 'default' right now")
    def test_vector_choice_delegates_to_picovector_text(self, mock_presto_module):
        _reset_vector_mocks()
        theme = CompressoTheme()
        theme.font_choice = "atkinson"
        display = _mock_display()
        theme.setup(display, dpi_scale_factor=2)
        display.rectangle.reset_mock()

        theme.text(display, "hello", 10, 20, rel_scale=1)

        vector = picovector.PicoVector.return_value
        vector.text.assert_called_once()
        display.rectangle.assert_not_called()  # not the font5x5 path

    def test_default_choice_measures_via_font_module(self, mock_presto_module):
        theme = CompressoTheme()
        display = _mock_display()
        theme.setup(display, dpi_scale_factor=2)

        width, height = theme.measure_text(display, "0709", rel_scale=3)

        expected_units = sum(font5x5.GLYPHS[c][0] + font5x5.GLYPH_GAP for c in "0709")
        assert width == expected_units * 6
        assert height == font5x5.CELL_HEIGHT * 6

    @pytest.mark.skip(reason="Atkinson/Inter gated off -- FONT_CHOICES has only 'default' right now")
    def test_vector_choice_measures_via_picovector(self, mock_presto_module):
        _reset_vector_mocks()
        theme = CompressoTheme()
        theme.font_choice = "inter"
        display = _mock_display()
        theme.setup(display, dpi_scale_factor=2)
        picovector.PicoVector.return_value.measure_text.return_value = (0, 0, 123, 20)

        width, _ = theme.measure_text(display, "hello", rel_scale=1)

        assert width == 123


class TestApplyFontChoice:
    @pytest.mark.skip(reason="Atkinson/Inter gated off -- FONT_CHOICES has only 'default' right now")
    def test_switches_to_a_vector_font(self, mock_presto_module):
        _reset_vector_mocks()
        theme = CompressoTheme()
        display = _mock_display()
        theme.setup(display, dpi_scale_factor=2)  # boots with the default font

        theme.apply_font_choice(display, "atkinson")

        assert theme.font_choice == "atkinson"
        assert theme.font == CompressoTheme.FONT_CHOICES["atkinson"]
        assert theme._use_vector_font_rendering is True
        assert theme.base_font_scale == CompressoTheme.VECTOR_FONT_SIZE
        picovector.PicoVector.return_value.set_font.assert_any_call(
            theme.font, theme.base_font_scale
        )

    @pytest.mark.skip(reason="Atkinson/Inter gated off -- FONT_CHOICES has only 'default' right now")
    def test_switches_back_to_default_and_restores_bitmap_metrics(self, mock_presto_module):
        # Regression check: apply_font_choice() must re-derive
        # base_font_scale/base_text_height/base_line_height for the target
        # choice, not just leave whatever the vector font's setup() left in
        # place -- otherwise switching back to "default" at runtime would
        # keep rendering font5x5 at the vector font's pixel-size scale.
        _reset_vector_mocks()
        theme = CompressoTheme()
        theme.font_choice = "inter"
        display = _mock_display()
        theme.setup(display, dpi_scale_factor=2)
        assert theme.base_font_scale == CompressoTheme.VECTOR_FONT_SIZE  # sanity: vector active

        theme.apply_font_choice(display, "default")

        assert theme.font_choice == "default"
        assert theme.font == "bitmap8"
        assert theme._use_vector_font_rendering is False
        assert theme.base_font_scale == 2  # DefaultTheme's 1, dpi-scaled by 2
        assert theme.base_text_height == font5x5.CELL_HEIGHT * 2
        assert theme.base_line_height == font5x5.LINE_HEIGHT * 2

    def test_unknown_choice_falls_back_to_default(self, mock_presto_module):
        _reset_vector_mocks()
        theme = CompressoTheme()
        display = _mock_display()
        theme.setup(display, dpi_scale_factor=2)

        theme.apply_font_choice(display, "not-a-real-font")

        assert theme.font_choice == "default"
        assert theme._use_vector_font_rendering is False
