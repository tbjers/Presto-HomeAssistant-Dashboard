"""
Tests for dashboard.tiles.
"""

from unittest import mock

import pytest

from tmos import Region

from dashboard import palette, topics
from dashboard.tiles import DateTimeTile, DimmableLightTile, SceneButtonTile, ToggleTile, ValueTile


def _pens():
    return palette.PenCache(mock.Mock())


def _region():
    return Region(0, 0, 114, 114)


def _press_and_release(tile, factory, x=10, y=10):
    tile.process_touch_state(_touch(factory, True, x, y))
    tile.process_touch_state(_touch(factory, False, x, y))


def _touch(factory, state, x=0, y=0):
    t = factory()
    t.state = state
    t.x = x
    t.y = y
    return t


THRESHOLDS = [
    (18, palette.SKY_SCALE),
    (25, palette.GREEN_SCALE),
    (28, palette.AMBER_SCALE),
    (None, palette.ROSE_SCALE),
]


class TestValueTile:
    def test_set_state_extracts_value(self):
        tile = ValueTile(_region(), _pens(), "OFFICE", unit="C")
        tile.set_state({"value": 21.5, "unit": "C"})
        assert tile._value == 21.5

    def test_set_state_none_clears_value(self):
        tile = ValueTile(_region(), _pens(), "OFFICE", initial_value=21.5)
        tile.set_state(None)
        assert tile._value is None

    def test_draw_uses_neutral_scale_when_value_is_none(self):
        display = mock.Mock()
        tile = ValueTile(_region(), palette.PenCache(display), "OFFICE", thresholds=THRESHOLDS)

        tile.draw(display, theme=mock.Mock(padding=8))

        pens_used = [tuple(c.args) for c in display.create_pen.call_args_list]
        assert palette.NEUTRAL_SCALE[0] in pens_used  # background

    def test_draw_picks_matching_threshold_scale(self):
        display = mock.Mock()
        tile = ValueTile(
            _region(), palette.PenCache(display), "OFFICE", thresholds=THRESHOLDS, initial_value=30
        )

        tile.draw(display, theme=mock.Mock(padding=8))

        pens_used = [tuple(c.args) for c in display.create_pen.call_args_list]
        assert palette.ROSE_SCALE[0] in pens_used  # 30 >= 28 -> ROSE

    def test_draw_renders_value_and_label_text(self):
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        tile = ValueTile(_region(), palette.PenCache(display), "OFFICE", unit="C", initial_value=21)

        tile.draw(display, theme)

        rendered = [c.args[1] for c in theme.text.call_args_list]
        assert "21" in rendered
        assert "OFFICE" in rendered
        assert "°C" in rendered


class TestDateTimeTile:
    def test_draw_formats_time_and_date_from_8_tuple(self):
        # MicroPython's time.gmtime() shape: no tm_isdst field.
        os = mock.Mock()
        os.localtime.return_value = (2026, 7, 24, 9, 5, 0, 4, 205)  # Friday
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        tile = DateTimeTile(_region(), palette.PenCache(display), os)

        tile.draw(display, theme)

        rendered = [c.args[1] for c in theme.text.call_args_list]
        assert "09:05" in rendered
        assert "Friday, 24.07." in rendered

    def test_draw_formats_time_and_date_from_9_tuple(self):
        # CPython's time.gmtime() shape: includes a trailing tm_isdst field.
        os = mock.Mock()
        os.localtime.return_value = (2026, 12, 1, 23, 59, 0, 1, 335, 0)  # Tuesday
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        tile = DateTimeTile(_region(), palette.PenCache(display), os)

        tile.draw(display, theme)

        rendered = [c.args[1] for c in theme.text.call_args_list]
        assert "23:59" in rendered
        assert "Tuesday, 01.12." in rendered


class TestToggleTile:
    def test_set_state_on(self):
        tile = ToggleTile(_region(), _pens(), "switch", "fan", "FAN", mock.Mock())
        tile.set_state({"state": "on"})
        assert tile._state is True

    def test_set_state_off(self):
        tile = ToggleTile(_region(), _pens(), "switch", "fan", "FAN", mock.Mock())
        tile.set_state({"state": "off"})
        assert tile._state is False

    def test_set_state_unknown_or_missing_is_none(self):
        tile = ToggleTile(_region(), _pens(), "switch", "fan", "FAN", mock.Mock())
        tile.set_state({"state": "??"})
        assert tile._state is None
        tile.set_state(None)
        assert tile._state is None

    def test_tap_on_switch_publishes_switch_command(self, mock_touch_factory):
        mqtt = mock.Mock()
        tile = ToggleTile(_region(), _pens(), "switch", "fan", "FAN", mqtt, initial_state=False)

        _press_and_release(tile, mock_touch_factory)

        mqtt.publish.assert_called_once_with(
            topics.set_topic("switch", "fan"), topics.format_switch_command(True)
        )

    def test_tap_on_light_publishes_light_command(self, mock_touch_factory):
        mqtt = mock.Mock()
        tile = ToggleTile(_region(), _pens(), "light", "lamp", "LAMP", mqtt, initial_state=True)

        _press_and_release(tile, mock_touch_factory)

        mqtt.publish.assert_called_once_with(
            topics.set_topic("light", "lamp"), topics.format_light_command(False)
        )

    def test_tap_with_unknown_state_defaults_to_turning_on(self, mock_touch_factory):
        mqtt = mock.Mock()
        tile = ToggleTile(_region(), _pens(), "light", "lamp", "LAMP", mqtt, initial_state=None)

        _press_and_release(tile, mock_touch_factory)

        mqtt.publish.assert_called_once_with(
            topics.set_topic("light", "lamp"), topics.format_light_command(True)
        )

    def test_touch_outside_region_does_not_publish(self, mock_touch_factory):
        mqtt = mock.Mock()
        tile = ToggleTile(_region(), _pens(), "light", "lamp", "LAMP", mqtt, initial_state=False)

        _press_and_release(tile, mock_touch_factory, x=9999, y=9999)

        mqtt.publish.assert_not_called()

    def test_draw_reflects_on_state(self):
        display = mock.Mock()
        tile = ToggleTile(_region(), palette.PenCache(display), "light", "lamp", "LAMP", mock.Mock())
        tile.set_state({"state": "on"})

        tile.draw(display, theme=mock.Mock(padding=8))

        pens_used = [tuple(c.args) for c in display.create_pen.call_args_list]
        assert palette.GREEN_400 in pens_used


class TestSceneButtonTile:
    def test_tap_publishes_empty_scene_command(self, mock_touch_factory):
        mqtt = mock.Mock()
        tile = SceneButtonTile(_region(), _pens(), "scene", "good_night", "GOOD NIGHT", mqtt)

        _press_and_release(tile, mock_touch_factory)

        mqtt.publish.assert_called_once_with(
            topics.set_topic("scene", "good_night"), topics.format_scene_command()
        )

    def test_flash_fraction_is_full_immediately_after_trigger(self, mock_touch_factory):
        tile = SceneButtonTile(_region(), _pens(), "scene", "good_night", "GOOD NIGHT", mock.Mock())
        _press_and_release(tile, mock_touch_factory)
        assert tile._flash_fraction() == 1.0

    def test_flash_fraction_decays_partway_through(self, mock_touch_factory):
        tile = SceneButtonTile(_region(), _pens(), "scene", "good_night", "GOOD NIGHT", mock.Mock())
        _press_and_release(tile, mock_touch_factory)

        # Simulate half the flash duration passing without a real sleep.
        tile._flash_started_at -= SceneButtonTile.FLASH_DURATION_MS // 2

        assert tile._flash_fraction() == 0.5

    def test_flash_fraction_is_quantized_to_flash_steps(self, mock_touch_factory):
        tile = SceneButtonTile(_region(), _pens(), "scene", "good_night", "GOOD NIGHT", mock.Mock())
        _press_and_release(tile, mock_touch_factory)

        # An arbitrary elapsed time should still land on one of the fixed
        # quantized steps, not a continuously-varying value (see
        # palette.lerp_color's docstring for why: unbounded distinct pens).
        tile._flash_started_at -= 130  # not a clean fraction of FLASH_DURATION_MS

        fraction = tile._flash_fraction()
        step = 1.0 / SceneButtonTile.FLASH_STEPS
        assert fraction == pytest.approx(round(fraction / step) * step)

    def test_flash_fraction_expires_after_duration(self, mock_touch_factory):
        tile = SceneButtonTile(_region(), _pens(), "scene", "good_night", "GOOD NIGHT", mock.Mock())
        _press_and_release(tile, mock_touch_factory)

        # Simulate time passing without a real sleep.
        tile._flash_started_at -= SceneButtonTile.FLASH_DURATION_MS + 1

        assert tile._flash_fraction() == 0.0

    def test_flash_fraction_is_zero_when_never_triggered(self):
        tile = SceneButtonTile(_region(), _pens(), "scene", "good_night", "GOOD NIGHT", mock.Mock())
        assert tile._flash_fraction() == 0.0

    def test_draw_reflects_flash_state(self):
        display = mock.Mock()
        tile = SceneButtonTile(
            _region(), palette.PenCache(display), "scene", "good_night", "GOOD NIGHT", mock.Mock()
        )
        import time

        tile._flash_started_at = time.ticks_ms()

        tile.draw(display, theme=mock.Mock(padding=8))

        pens_used = [tuple(c.args) for c in display.create_pen.call_args_list]
        assert palette.AMBER_400 in pens_used


class TestDimmableLightTile:
    def test_set_state_extracts_state_and_brightness(self):
        tile = DimmableLightTile(
            _region(), _pens(), "light", "ceiling", "CEILING", mock.Mock(), mock.Mock()
        )
        tile.set_state({"state": "on", "brightness": 180})
        assert tile._state is True
        assert tile._brightness == 180

    def test_tap_opens_brightness_modal_via_window_manager(self, mock_touch_factory):
        mqtt = mock.Mock()
        window_manager = mock.Mock()
        tile = DimmableLightTile(
            _region(), _pens(), "light", "ceiling", "CEILING", mqtt, window_manager,
            initial_state=True, initial_brightness=90,
        )

        _press_and_release(tile, mock_touch_factory)

        window_manager.show_modal_page.assert_called_once()
        (modal,), _ = window_manager.show_modal_page.call_args
        assert modal.domain == "light"
        assert modal.slug == "ceiling"
        assert modal.label == "CEILING"
        assert modal._mqtt is mqtt
        assert modal._initial_brightness == 90

    def test_draw_reflects_on_state(self):
        display = mock.Mock()
        tile = DimmableLightTile(
            _region(), palette.PenCache(display), "light", "ceiling", "CEILING",
            mock.Mock(), mock.Mock(), initial_state=False,
        )

        tile.draw(display, theme=mock.Mock(padding=8))

        pens_used = [tuple(c.args) for c in display.create_pen.call_args_list]
        assert palette.GRAY_900 in pens_used
