"""
Tests for dashboard.modal: SliderControl, VerticalSliderControl, PowerButton,
DetailModalPage, LightBrightnessModal.
"""

from unittest import mock

import picovector
import pytest

from tmos import Region

from dashboard import corners, grid, icons, palette, topics
from dashboard.modal import (
    DetailModalPage,
    LightBrightnessModal,
    PowerButton,
    SliderControl,
    VerticalSliderControl,
)


def _touch(factory, state, x=0, y=0):
    t = factory()
    t.state = state
    t.x = x
    t.y = y
    return t


def _pens():
    return palette.PenCache(mock.Mock())


# A plain int, not an rgb tuple -- by the time any Page's draw() runs in
# production, Theme.setup()'s pen-conversion loop (tmos_ui.py) has already
# turned background_pen into a real pen handle via display.create_pen(),
# same as any other _pens-listed attribute. Using a raw palette tuple here
# previously masked a real bug: VerticalSliderControl/PowerButton.draw()
# passed theme.background_pen through self._pens.get() a second time,
# which expects an unconverted rgb tuple and TypeErrors trying to unpack
# an already-converted int pen handle -- caught only by the on-device
# smoke test (mocked displays don't complain about *anything unpacking).
_BACKGROUND_PEN_HANDLE = 999999


# Matches theme.text_scale(3) in production -- see dashboard/theme.py's
# module docstring (base_font_scale=2 at our fixed dpi_scale_factor=2,
# *3 for tiles.py's big-value rel_scale).
_PIXEL_SIZE = 6


def _theme(style="smooth", radius="large", background_pen=_BACKGROUND_PEN_HANDLE, pixel_size=_PIXEL_SIZE):
    # A bare mock.Mock() would make theme.text_scale(3) return a Mock
    # object rather than a usable int, so draw()-exercising tests need
    # this instead of mock.Mock().
    theme = mock.Mock()
    theme.corner_style = style
    theme.corner_radius = radius
    theme.background_pen = background_pen
    theme.text_scale = mock.Mock(return_value=pixel_size)
    return theme


def _reset_vector_mocks():
    # Polygon()/PicoVector() are Mock classes shared across the whole test
    # session (see tests/conftest.py) -- reset their recorded calls so
    # assertions here don't pick up state from other tests (same idiom as
    # tests/test_splash.py's _os() helper).
    picovector.Polygon.reset_mock()
    picovector.Polygon.return_value.reset_mock()
    picovector.PicoVector.reset_mock()
    picovector.PicoVector.return_value.reset_mock()


class TestSliderControlDragging:
    def test_touch_outside_region_does_not_start_a_drag(self, mock_touch_factory):
        region = Region(100, 100, 200, 40)
        slider = SliderControl(region, 0, 255, 50, _pens())

        slider.process_touch_state(_touch(mock_touch_factory, True, x=50, y=50))

        assert slider.value == 50  # unchanged

    def test_touch_starting_inside_updates_value_immediately(self, mock_touch_factory):
        region = Region(100, 100, 200, 40)
        slider = SliderControl(region, 0, 255, 50, _pens())

        # Touch at the region's left edge -> fraction 0 -> min_value.
        slider.process_touch_state(_touch(mock_touch_factory, True, x=100, y=110))

        assert slider.value == 0

    def test_touch_at_region_midpoint_gives_midpoint_value(self, mock_touch_factory):
        region = Region(0, 0, 200, 40)
        slider = SliderControl(region, 0, 255, 0, _pens())

        slider.process_touch_state(_touch(mock_touch_factory, True, x=100, y=10))

        assert slider.value == pytest.approx(127.5)

    def test_drag_started_inside_can_continue_past_the_region_edge_clamped(self, mock_touch_factory):
        region = Region(0, 0, 200, 40)
        slider = SliderControl(region, 0, 255, 0, _pens())

        slider.process_touch_state(_touch(mock_touch_factory, True, x=10, y=10))
        slider.process_touch_state(_touch(mock_touch_factory, True, x=9999, y=10))

        assert slider.value == 255  # clamped, not out of range

    def test_drag_started_outside_is_not_grabbed_by_moving_into_the_region(self, mock_touch_factory):
        region = Region(100, 100, 200, 40)
        slider = SliderControl(region, 0, 255, 50, _pens())

        # First tick: touch is down, but outside the region.
        slider.process_touch_state(_touch(mock_touch_factory, True, x=0, y=0))
        # Second tick: same touch drags into the region while still held down.
        slider.process_touch_state(_touch(mock_touch_factory, True, x=150, y=110))

        assert slider.value == 50  # still unchanged -- drag never started

    def test_on_change_fires_on_every_tick_while_dragging(self, mock_touch_factory):
        region = Region(0, 0, 200, 40)
        slider = SliderControl(region, 0, 255, 0, _pens())
        on_change = mock.Mock()
        slider.on_change = on_change

        slider.process_touch_state(_touch(mock_touch_factory, True, x=0, y=10))
        slider.process_touch_state(_touch(mock_touch_factory, True, x=100, y=10))

        assert on_change.call_count == 2
        on_change.assert_called_with(pytest.approx(127.5))

    def test_on_commit_fires_once_on_release_with_final_value(self, mock_touch_factory):
        region = Region(0, 0, 200, 40)
        slider = SliderControl(region, 0, 255, 0, _pens())
        on_commit = mock.Mock()
        slider.on_commit = on_commit

        slider.process_touch_state(_touch(mock_touch_factory, True, x=100, y=10))  # start drag, inside
        slider.process_touch_state(_touch(mock_touch_factory, True, x=9999, y=10))  # drag to max, clamped
        on_commit.assert_not_called()

        slider.process_touch_state(_touch(mock_touch_factory, False, x=9999, y=10))
        on_commit.assert_called_once_with(255)

    def test_on_commit_not_fired_again_without_a_new_drag(self, mock_touch_factory):
        region = Region(0, 0, 200, 40)
        slider = SliderControl(region, 0, 255, 0, _pens())
        on_commit = mock.Mock()
        slider.on_commit = on_commit

        slider.process_touch_state(_touch(mock_touch_factory, True, x=100, y=10))
        slider.process_touch_state(_touch(mock_touch_factory, False, x=100, y=10))
        slider.process_touch_state(_touch(mock_touch_factory, False, x=100, y=10))

        on_commit.assert_called_once()

    def test_initial_value_is_clamped_to_range(self, mock_touch_factory):
        region = Region(0, 0, 200, 40)
        slider = SliderControl(region, 0, 255, 9999, _pens())
        assert slider.value == 255

        slider2 = SliderControl(region, 0, 255, -50, _pens())
        assert slider2.value == 0


class TestSliderControlDraw:
    def test_draw_paints_track_fill_and_handle(self):
        display = mock.Mock()
        region = Region(0, 0, 200, 40)
        pens = palette.PenCache(display)
        slider = SliderControl(region, 0, 255, 127, pens)

        slider.draw(display, theme=_theme())

        # Track + fill + handle each set a pen and draw something.
        assert display.set_pen.call_count == 3
        assert display.rectangle.call_count == 2  # track background + fill
        display.circle.assert_called_once()

    def test_draw_at_minimum_value_skips_fill_rectangle(self):
        display = mock.Mock()
        region = Region(0, 0, 200, 40)
        pens = palette.PenCache(display)
        slider = SliderControl(region, 0, 255, 0, pens)

        slider.draw(display, theme=_theme())

        assert display.rectangle.call_count == 1  # only the track background


class TestVerticalSliderControlDragging:
    def test_touch_near_top_gives_a_high_value(self, mock_touch_factory):
        region = Region(0, 0, 40, 200)
        slider = VerticalSliderControl(region, 0, 255, 0, _pens())

        slider.process_touch_state(_touch(mock_touch_factory, True, x=10, y=0))

        assert slider.value == 255

    def test_touch_near_bottom_gives_a_low_value(self, mock_touch_factory):
        region = Region(0, 0, 40, 200)
        slider = VerticalSliderControl(region, 0, 255, 255, _pens())

        # y=199, not 200 -- is_within() treats the region as [y, y+height),
        # so y=200 is just outside and would never start a drag.
        slider.process_touch_state(_touch(mock_touch_factory, True, x=10, y=199))

        assert slider.value == pytest.approx(1.275)

    def test_touch_at_region_midpoint_gives_midpoint_value(self, mock_touch_factory):
        region = Region(0, 0, 40, 200)
        slider = VerticalSliderControl(region, 0, 255, 0, _pens())

        slider.process_touch_state(_touch(mock_touch_factory, True, x=10, y=100))

        assert slider.value == pytest.approx(127.5)

    def test_touch_must_start_inside_region_to_begin_a_drag(self, mock_touch_factory):
        region = Region(100, 100, 40, 200)
        slider = VerticalSliderControl(region, 0, 255, 50, _pens())

        slider.process_touch_state(_touch(mock_touch_factory, True, x=0, y=0))

        assert slider.value == 50  # unchanged -- touch started outside


class TestVerticalSliderControlDraw:
    def test_draw_paints_rounded_track_and_fill_with_no_handle(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(0, 0, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 127, pens)

        slider.draw(display, theme=_theme())

        polygon = picovector.Polygon.return_value
        vector = picovector.PicoVector.return_value
        assert polygon.rectangle.call_count == 2  # track + fill
        assert vector.draw.call_count == 2
        display.circle.assert_not_called()  # no handle

    def test_draw_fills_green_when_is_on(self):
        _reset_vector_mocks()
        display = mock.Mock()
        display.create_pen.side_effect = lambda *rgb: rgb  # distinguish pens by color
        region = Region(0, 0, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 127, pens)
        slider.is_on = True

        slider.draw(display, theme=_theme())

        pen_calls = [c.args[0] for c in display.set_pen.call_args_list]
        assert palette.GREEN_400 in pen_calls
        assert palette.GRAY_700 not in pen_calls

    def test_draw_fills_gray_when_not_is_on(self):
        _reset_vector_mocks()
        display = mock.Mock()
        display.create_pen.side_effect = lambda *rgb: rgb  # distinguish pens by color
        region = Region(0, 0, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 127, pens)
        slider.is_on = False

        slider.draw(display, theme=_theme())

        pen_calls = [c.args[0] for c in display.set_pen.call_args_list]
        assert palette.GRAY_700 in pen_calls
        assert palette.GREEN_400 not in pen_calls

    def test_draw_at_minimum_value_skips_the_fill(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(0, 0, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 0, pens)

        slider.draw(display, theme=_theme())

        polygon = picovector.Polygon.return_value
        assert polygon.rectangle.call_count == 1  # only the track

    def test_draw_at_maximum_value_fill_matches_track_geometry(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(5, 10, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 255, pens)

        slider.draw(display, theme=_theme())

        polygon = picovector.Polygon.return_value
        track_call, fill_call = polygon.rectangle.call_args_list
        assert track_call.args == (5, 10, 40, 200)
        assert fill_call.args == (5, 10, 40, 200)  # fill covers the full track

    def test_draw_reuses_cached_vector_and_track_polygon_across_frames(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(0, 0, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 127, pens)

        slider.draw(display, theme=_theme())
        slider.draw(display, theme=_theme())

        # PicoVector()/the track's Polygon() are each constructed once and
        # reused -- Polygon() is called 3 times total (1 track + 2 fills),
        # not 4.
        assert picovector.PicoVector.call_count == 1
        assert picovector.Polygon.call_count == 3


class TestVerticalSliderControlBlockyDraw:
    def test_square_radius_draws_a_plain_rect_regardless_of_style(self):
        for style in ("smooth", "blocky"):
            _reset_vector_mocks()
            display = mock.Mock()
            region = Region(0, 0, 40, 200)
            pens = palette.PenCache(display)
            slider = VerticalSliderControl(region, 0, 255, 0, pens)  # no fill

            slider.draw(display, theme=_theme(style=style, radius="square"))

            picovector.PicoVector.assert_not_called()
            picovector.Polygon.assert_not_called()
            assert display.rectangle.call_args_list == [mock.call(0, 0, 40, 200)]

    def test_blocky_style_never_touches_picovector(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(0, 0, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 127, pens)

        slider.draw(display, theme=_theme(style="blocky", radius="small"))

        picovector.PicoVector.assert_not_called()
        picovector.Polygon.assert_not_called()

    def test_track_is_drawn_as_a_plain_rectangle_plus_corner_notches(self):
        display = mock.Mock()
        region = Region(0, 0, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 0, pens)  # 0 -> no fill

        slider.draw(display, theme=_theme(style="blocky", radius="small"))

        # Full track rect, then 4 corner notches (chunkiest level = 1
        # notch/corner) all erased to the theme's background pen.
        assert display.rectangle.call_args_list[0].args == (0, 0, 40, 200)
        assert display.rectangle.call_count == 1 + 4

    def test_fill_bottom_corners_always_erase_to_background(self):
        display = mock.Mock()
        display.create_pen.side_effect = lambda *rgb: rgb
        region = Region(0, 0, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 64, pens)  # partial fill

        slider.draw(display, theme=_theme(style="blocky", radius="small"))

        bg_pen = _BACKGROUND_PEN_HANDLE
        # Bottom-left/bottom-right fill notches (the last two rectangle()
        # calls) must use the true background pen, since the fill's bottom
        # edge always coincides with the track's own already-background-cut
        # bottom corners regardless of fill fraction.
        bottom_calls = display.rectangle.call_args_list[-2:]
        pen_calls = display.set_pen.call_args_list
        # Find the set_pen call immediately preceding each bottom notch.
        rect_index = {id(c): i for i, c in enumerate(display.rectangle.call_args_list)}
        for call in bottom_calls:
            i = rect_index[id(call)]
            assert pen_calls[i].args == (bg_pen,)

    def test_fill_top_corners_erase_to_track_color_when_partially_filled(self):
        display = mock.Mock()
        display.create_pen.side_effect = lambda *rgb: rgb
        region = Region(0, 0, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 64, pens)  # partial fill

        slider.draw(display, theme=_theme(style="blocky", radius="small"))

        track_pen = pens.get(palette.GRAY_800)
        # First two fill-notch rectangle() calls are the fill's top corners.
        fill_rect_calls = display.rectangle.call_args_list[6:]  # after track rect + 4 notches + fill rect
        top_calls = fill_rect_calls[:2]
        pen_calls = display.set_pen.call_args_list
        rect_index = {id(c): i for i, c in enumerate(display.rectangle.call_args_list)}
        for call in top_calls:
            i = rect_index[id(call)]
            assert pen_calls[i].args == (track_pen,)

    def test_fill_top_corners_erase_to_background_when_fully_filled(self):
        display = mock.Mock()
        display.create_pen.side_effect = lambda *rgb: rgb
        region = Region(0, 0, 40, 200)
        pens = palette.PenCache(display)
        slider = VerticalSliderControl(region, 0, 255, 255, pens)  # full fill

        slider.draw(display, theme=_theme(style="blocky", radius="small"))

        bg_pen = _BACKGROUND_PEN_HANDLE
        fill_rect_calls = display.rectangle.call_args_list[6:]
        top_calls = fill_rect_calls[:2]
        pen_calls = display.set_pen.call_args_list
        rect_index = {id(c): i for i, c in enumerate(display.rectangle.call_args_list)}
        for call in top_calls:
            i = rect_index[id(call)]
            assert pen_calls[i].args == (bg_pen,)


class TestPowerButtonDraw:
    def test_draw_uses_on_colors_when_is_on(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(0, 0, 114, 53)
        pens = palette.PenCache(display)
        button = PowerButton(region, pens)
        button.is_on = True

        button.draw(display, theme=_theme())

        pen_calls = [c.args[0] for c in display.set_pen.call_args_list]
        assert pens.get(palette.GREEN_400) in pen_calls
        assert pens.get(palette.GREEN_900) in pen_calls

    def test_draw_uses_off_colors_when_not_is_on(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(0, 0, 114, 53)
        pens = palette.PenCache(display)
        button = PowerButton(region, pens)
        button.is_on = False

        button.draw(display, theme=_theme())

        pen_calls = [c.args[0] for c in display.set_pen.call_args_list]
        assert pens.get(palette.GRAY_900) in pen_calls
        assert pens.get(palette.GRAY_600) in pen_calls

    def test_icon_polygon_built_from_outline_and_stem_at_construction(self):
        _reset_vector_mocks()
        region = Region(0, 0, 114, 53)
        button = PowerButton(region, _pens())

        # _bg_polygon is built lazily in draw() now (its radius depends on
        # theme, not known at construction -- see PowerButton's own
        # docstring), so only the icon polygon exists at this point:
        # .path() for the outline, one .rectangle() for the stem.
        polygon = picovector.Polygon.return_value
        assert len(polygon.path.call_args.args) == len(icons.MDI_POWER_OUTLINE)
        assert polygon.rectangle.call_count == 1  # stem only, no bg yet
        assert button._bg_polygon is None

    def test_bg_polygon_built_lazily_on_first_draw(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(0, 0, 114, 53)
        button = PowerButton(region, _pens())

        button.draw(display, theme=_theme())

        polygon = picovector.Polygon.return_value
        assert polygon.rectangle.call_count == 2  # stem + now the bg too
        assert button._bg_polygon is polygon

    def test_bg_polygon_cached_across_frames(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(0, 0, 114, 53)
        button = PowerButton(region, _pens())

        button.draw(display, theme=_theme())
        button.draw(display, theme=_theme())

        polygon = picovector.Polygon.return_value
        assert polygon.rectangle.call_count == 2  # not rebuilt on the 2nd draw


class TestPowerButtonBlockyDraw:
    def test_blocky_style_draws_background_as_plain_rect_plus_notches(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(0, 0, 114, 53)
        pens = palette.PenCache(display)
        button = PowerButton(region, pens)
        button.is_on = True

        button.draw(display, theme=_theme(style="blocky", radius="small"))

        # Background polygon is never drawn via PicoVector at this level --
        # only the icon (built once in __init__, drawn via self._vector).
        vector = picovector.PicoVector.return_value
        assert vector.draw.call_count == 1  # icon only, not the bg_polygon
        assert display.rectangle.call_args_list[0].args == (0, 0, 114, 53)
        assert display.rectangle.call_count == 1 + 4  # bg rect + 4 corner notches

    def test_icon_still_drawn_via_picovector_when_blocky(self):
        _reset_vector_mocks()
        display = mock.Mock()
        region = Region(0, 0, 114, 53)
        button = PowerButton(region, _pens())

        button.draw(display, theme=_theme(style="blocky", radius="small"))

        vector = picovector.PicoVector.return_value
        vector.draw.assert_called_once_with(button._icon_polygon)


class TestDetailModalPage:
    def _window_manager(self):
        window_manager = mock.Mock()
        window_manager.theme.padding = 8
        window_manager.theme.control_height = 53
        return window_manager

    def test_setup_adds_a_close_button(self):
        page = DetailModalPage()
        window_manager = self._window_manager()

        page.setup(Region(0, 0, 480, 480), window_manager)

        assert len(page._controls) == 1

    def test_closing_clears_the_modal_page(self):
        page = DetailModalPage()
        window_manager = self._window_manager()
        page.setup(Region(0, 0, 480, 480), window_manager)
        close_button = page._controls[0]

        close_button.on_button_up()

        window_manager.clear_modal_page.assert_called_once()

    def test_closing_forces_the_underlying_page_to_redraw(self):
        # TmOS's own show_modal_page/clear_modal_page don't run the usual
        # will_show()/will_hide() page-transition dance for the page
        # underneath a modal (see dashboard/modal.py's _close_modal
        # docstring) -- without explicitly calling will_show() here, a
        # DashboardPage's tiles would stay marked clean from before the
        # modal opened and never repaint over its leftover pixels.
        page = DetailModalPage()
        window_manager = self._window_manager()
        underlying_page = mock.Mock()
        window_manager.current_page = underlying_page
        page.setup(Region(0, 0, 480, 480), window_manager)
        close_button = page._controls[0]

        close_button.on_button_up()

        underlying_page.will_show.assert_called_once()

    def test_closing_with_no_current_page_does_not_raise(self):
        page = DetailModalPage()
        window_manager = self._window_manager()
        window_manager.current_page = None
        page.setup(Region(0, 0, 480, 480), window_manager)
        close_button = page._controls[0]

        close_button.on_button_up()  # should not raise


class TestLightBrightnessModal:
    def _window_manager(self):
        wm = mock.Mock()
        wm.theme.padding = 8
        wm.theme.control_height = 53
        return wm

    def test_setup_creates_slider_bound_to_initial_brightness(self):
        mqtt = mock.Mock()
        modal = LightBrightnessModal(
            "light", "ceiling_light", "CEILING", mqtt, _pens(), initial_brightness=64
        )
        modal.setup(Region(0, 0, 480, 480), self._window_manager())

        assert modal._slider.min_value == 0
        assert modal._slider.max_value == 255
        assert modal._slider.value == 64

    def test_none_initial_brightness_defaults_to_128(self):
        modal = LightBrightnessModal(
            "light", "ceiling_light", "CEILING", mock.Mock(), _pens(), initial_brightness=None
        )
        modal.setup(Region(0, 0, 480, 480), self._window_manager())

        assert modal._slider.value == 128

    def test_setup_positions_slider_power_and_label_via_the_grid(self):
        region = Region(0, 0, 480, 480)
        modal = LightBrightnessModal("light", "ceiling_light", "CEILING", mock.Mock(), _pens())
        modal.setup(region, self._window_manager())

        assert modal._slider.region == grid.cell_region(region, col=2, row=2, colspan=4, rowspan=10)
        assert modal._power_button.region == grid.cell_region(
            region, col=2, row=12, colspan=4, rowspan=2
        )
        assert modal._label_region == grid.cell_region(region, col=8, row=2, colspan=7, rowspan=10)
        # The label group shares the slider's row/rowspan, which is what
        # makes vertically-centering it against the slider trivial.
        assert modal._label_region.y == modal._slider.region.y
        assert modal._label_region.height == modal._slider.region.height
        # At least one full empty grid column between the slider and the
        # label group.
        gap = modal._label_region.x - (modal._slider.region.x + modal._slider.region.width)
        assert gap >= grid.tile_size(480.0) + grid.GAP

    def test_setup_adds_close_button_slider_and_power_button(self):
        modal = LightBrightnessModal("light", "ceiling_light", "CEILING", mock.Mock(), _pens())
        modal.setup(Region(0, 0, 480, 480), self._window_manager())

        assert len(modal._controls) == 3

    def test_dragging_and_releasing_the_slider_publishes_the_light_command(self, mock_touch_factory):
        mqtt = mock.Mock()
        modal = LightBrightnessModal("light", "ceiling_light", "CEILING", mqtt, _pens())
        modal.setup(Region(0, 0, 480, 480), self._window_manager())

        slider_region = modal._slider.region
        touch_x = slider_region.x + 5
        modal._slider.process_touch_state(  # start drag, inside, near the top
            _touch(mock_touch_factory, True, x=touch_x, y=slider_region.y)
        )
        modal._slider.process_touch_state(
            _touch(mock_touch_factory, False, x=touch_x, y=slider_region.y)
        )

        mqtt.publish.assert_called_once_with(
            topics.set_topic("light", "ceiling_light"),
            topics.format_light_command(True, brightness=255),
        )

    def test_dragging_updates_display_brightness_live_without_publishing(self, mock_touch_factory):
        mqtt = mock.Mock()
        modal = LightBrightnessModal("light", "ceiling_light", "CEILING", mqtt, _pens())
        modal.setup(Region(0, 0, 480, 480), self._window_manager())

        slider_region = modal._slider.region
        touch_x = slider_region.x + 5
        modal._slider.process_touch_state(
            _touch(mock_touch_factory, True, x=touch_x, y=slider_region.y)
        )

        assert modal._display_brightness == 255
        assert modal._is_on is True
        mqtt.publish.assert_not_called()  # on_change must never publish

    def test_commit_marks_page_as_needing_update(self, mock_touch_factory):
        modal = LightBrightnessModal("light", "ceiling_light", "CEILING", mock.Mock(), _pens())
        modal.setup(Region(0, 0, 480, 480), self._window_manager())
        modal.needs_update = False

        slider_region = modal._slider.region
        modal._slider.process_touch_state(
            _touch(mock_touch_factory, True, x=slider_region.x, y=slider_region.y)
        )
        modal._slider.process_touch_state(
            _touch(mock_touch_factory, False, x=slider_region.x, y=slider_region.y)
        )

        assert modal.needs_update is True

    def test_power_toggle_from_on_publishes_off_with_no_brightness(self):
        mqtt = mock.Mock()
        modal = LightBrightnessModal(
            "light", "ceiling_light", "CEILING", mqtt, _pens(), initial_state=True
        )
        modal.setup(Region(0, 0, 480, 480), self._window_manager())

        modal._power_button.on_button_up()

        assert modal._is_on is False
        mqtt.publish.assert_called_once_with(
            topics.set_topic("light", "ceiling_light"), topics.format_light_command(False)
        )

    def test_power_toggle_from_off_publishes_on_with_no_brightness(self):
        mqtt = mock.Mock()
        modal = LightBrightnessModal(
            "light", "ceiling_light", "CEILING", mqtt, _pens(), initial_state=False
        )
        modal.setup(Region(0, 0, 480, 480), self._window_manager())

        modal._power_button.on_button_up()

        assert modal._is_on is True
        mqtt.publish.assert_called_once_with(
            topics.set_topic("light", "ceiling_light"), topics.format_light_command(True)
        )

    def test_power_toggle_marks_page_as_needing_update(self):
        modal = LightBrightnessModal(
            "light", "ceiling_light", "CEILING", mock.Mock(), _pens(), initial_state=False
        )
        modal.setup(Region(0, 0, 480, 480), self._window_manager())
        modal.needs_update = False

        modal._power_button.on_button_up()

        assert modal.needs_update is True

    def test_update_syncs_power_button_is_on_from_modal_state(self):
        modal = LightBrightnessModal(
            "light", "ceiling_light", "CEILING", mock.Mock(), _pens(), initial_state=False
        )
        modal.setup(Region(0, 0, 480, 480), self._window_manager())

        modal._is_on = True
        modal._update(os=mock.Mock())

        assert modal._power_button.is_on is True
        assert modal._slider.is_on is True

    @pytest.mark.parametrize(
        "is_on, brightness, expected",
        [
            (False, 128, "OFF"),
            (True, 0, "0%"),
            (True, 1, "0%"),  # rounds down -- "OFF" is reserved for is_on state, not brightness
            (True, 128, "50%"),
            (True, 255, "100%"),
        ],
    )
    def test_percentage_text(self, is_on, brightness, expected):
        modal = LightBrightnessModal(
            "light", "ceiling_light", "CEILING", mock.Mock(), _pens(),
            initial_brightness=brightness, initial_state=is_on,
        )

        assert modal._percentage_text() == expected
