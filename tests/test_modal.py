"""
Tests for dashboard.modal: SliderControl, DetailModalPage, LightBrightnessModal.
"""

from unittest import mock

import pytest

from tmos import Region

from dashboard import palette, topics
from dashboard.modal import DetailModalPage, LightBrightnessModal, SliderControl


def _touch(factory, state, x=0, y=0):
    t = factory()
    t.state = state
    t.x = x
    t.y = y
    return t


def _pens():
    return palette.PenCache(mock.Mock())


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

        slider.draw(display, theme=mock.Mock())

        # Track + fill + handle each set a pen and draw something.
        assert display.set_pen.call_count == 3
        assert display.rectangle.call_count == 2  # track background + fill
        display.circle.assert_called_once()

    def test_draw_at_minimum_value_skips_fill_rectangle(self):
        display = mock.Mock()
        region = Region(0, 0, 200, 40)
        pens = palette.PenCache(display)
        slider = SliderControl(region, 0, 255, 0, pens)

        slider.draw(display, theme=mock.Mock())

        assert display.rectangle.call_count == 1  # only the track background


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

    def test_dragging_and_releasing_the_slider_publishes_the_light_command(self, mock_touch_factory):
        mqtt = mock.Mock()
        modal = LightBrightnessModal("light", "ceiling_light", "CEILING", mqtt, _pens())
        modal.setup(Region(0, 0, 480, 480), self._window_manager())

        slider_region = modal._slider.region
        modal._slider.process_touch_state(  # start drag, inside
            _touch(mock_touch_factory, True, x=slider_region.x, y=slider_region.y + 5)
        )
        end_x = slider_region.x + slider_region.width + 999  # drag to max, clamped
        modal._slider.process_touch_state(
            _touch(mock_touch_factory, True, x=end_x, y=slider_region.y + 5)
        )
        modal._slider.process_touch_state(
            _touch(mock_touch_factory, False, x=end_x, y=slider_region.y + 5)
        )

        mqtt.publish.assert_called_once_with(
            topics.set_topic("light", "ceiling_light"),
            topics.format_light_command(True, brightness=255),
        )

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

    def test_setup_also_adds_the_inherited_close_button(self):
        modal = LightBrightnessModal("light", "ceiling_light", "CEILING", mock.Mock(), _pens())
        modal.setup(Region(0, 0, 480, 480), self._window_manager())

        # close button (from DetailModalPage.setup) + slider
        assert len(modal._controls) == 2
