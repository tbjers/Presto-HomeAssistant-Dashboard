"""
Tests for dashboard.tiles.
"""

from unittest import mock

import pytest

from tmos import Region

from dashboard import palette, topics
from dashboard.tiles import (
    DateTimeTile,
    DimmableLightTile,
    SceneButtonTile,
    ToggleTile,
    ValueTile,
    WeatherTile,
)


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

    def test_is_dirty_initially_true(self):
        tile = ValueTile(_region(), _pens(), "OFFICE")
        assert tile.is_dirty() is True

    def test_set_state_with_same_value_does_not_mark_dirty(self):
        tile = ValueTile(_region(), _pens(), "OFFICE", initial_value=21.5)
        tile.mark_clean()

        tile.set_state({"value": 21.5})

        assert tile.is_dirty() is False

    def test_set_state_with_different_value_marks_dirty(self):
        tile = ValueTile(_region(), _pens(), "OFFICE", initial_value=21.5)
        tile.mark_clean()

        tile.set_state({"value": 22.0})

        assert tile.is_dirty() is True

    def test_mark_dirty_forces_dirty_regardless_of_value(self):
        tile = ValueTile(_region(), _pens(), "OFFICE", initial_value=21.5)
        tile.mark_clean()

        tile.mark_dirty()

        assert tile.is_dirty() is True


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

    def test_is_dirty_initially_true(self):
        os = mock.Mock()
        os.localtime.return_value = (2026, 7, 24, 9, 5, 0, 4, 205)
        tile = DateTimeTile(_region(), _pens(), os)
        assert tile.is_dirty() is True

    def test_is_clean_when_minute_has_not_changed(self):
        os = mock.Mock()
        os.localtime.return_value = (2026, 7, 24, 9, 5, 0, 4, 205)
        tile = DateTimeTile(_region(), _pens(), os)

        tile.mark_clean()

        assert tile.is_dirty() is False

    def test_is_dirty_again_once_the_minute_changes(self):
        os = mock.Mock()
        os.localtime.return_value = (2026, 7, 24, 9, 5, 0, 4, 205)
        tile = DateTimeTile(_region(), _pens(), os)
        tile.mark_clean()

        os.localtime.return_value = (2026, 7, 24, 9, 6, 0, 4, 205)

        assert tile.is_dirty() is True

    def test_mark_dirty_forces_dirty_regardless_of_time(self):
        os = mock.Mock()
        os.localtime.return_value = (2026, 7, 24, 9, 5, 0, 4, 205)
        tile = DateTimeTile(_region(), _pens(), os)
        tile.mark_clean()

        tile.mark_dirty()

        assert tile.is_dirty() is True


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


class TestWeatherTile:
    def test_set_state_extracts_condition_and_temperature(self):
        tile = WeatherTile(_region(), _pens(), "OUTSIDE")
        tile.set_state({"condition": "sunny", "temperature": 21.5})
        assert tile._condition == "sunny"
        assert tile._temperature == 21.5

    def test_set_state_extracts_humidity(self):
        tile = WeatherTile(_region(), _pens(), "OUTSIDE")
        tile.set_state({"condition": "sunny", "temperature": 21.5, "humidity": 62})
        assert tile._humidity == 62

    def test_set_state_missing_humidity_is_none(self):
        tile = WeatherTile(_region(), _pens(), "OUTSIDE", initial_humidity=62)
        tile.set_state({"condition": "sunny", "temperature": 21.5})
        assert tile._humidity is None

    def test_set_state_none_clears_condition_and_temperature(self):
        tile = WeatherTile(_region(), _pens(), "OUTSIDE", initial_condition="sunny")
        tile.set_state(None)
        assert tile._condition is None
        assert tile._temperature is None

    def test_set_state_with_same_values_does_not_mark_dirty(self):
        tile = WeatherTile(
            _region(), _pens(), "OUTSIDE", initial_condition="sunny", initial_temperature=21.5,
            initial_humidity=62,
        )
        tile.mark_clean()

        tile.set_state({"condition": "sunny", "temperature": 21.5, "humidity": 62})

        assert tile.is_dirty() is False

    def test_set_state_with_different_condition_marks_dirty(self):
        tile = WeatherTile(
            _region(), _pens(), "OUTSIDE", initial_condition="sunny", initial_temperature=21.5
        )
        tile.mark_clean()

        tile.set_state({"condition": "rainy", "temperature": 21.5})

        assert tile.is_dirty() is True

    def test_set_state_with_different_humidity_marks_dirty(self):
        tile = WeatherTile(
            _region(), _pens(), "OUTSIDE", initial_condition="sunny", initial_temperature=21.5,
            initial_humidity=62,
        )
        tile.mark_clean()

        tile.set_state({"condition": "sunny", "temperature": 21.5, "humidity": 70})

        assert tile.is_dirty() is True

    def test_draw_renders_temperature_and_label_text(self):
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        tile = WeatherTile(
            _region(), palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=21.5,
        )

        tile.draw(display, theme)

        rendered = [c.args[1] for c in theme.text.call_args_list]
        assert "22" in rendered  # rounded, no unit configured -> no degree symbol
        assert "OUTSIDE" in rendered

    def test_draw_appends_unit_when_set(self):
        # Mirrors ValueTile's own convention (see its draw()): the unit is a
        # separate, smaller, dimmed text next to the value -- not baked into
        # one big string -- so measure_text needs a real (width, height)
        # return value, same as TestValueTile's equivalent tests.
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        tile = WeatherTile(
            _region(), palette.PenCache(display), "OUTSIDE", unit="F",
            initial_condition="sunny", initial_temperature=79,
        )

        tile.draw(display, theme)

        rendered = [c.args[1] for c in theme.text.call_args_list]
        assert "79" in rendered
        assert "°F" in rendered

    def test_draw_unit_is_dimmed_relative_to_the_value(self):
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        tile = WeatherTile(
            _region(), palette.PenCache(display), "OUTSIDE", unit="F",
            initial_condition="sunny", initial_temperature=79,
        )

        tile.draw(display, theme)

        pens_used = [tuple(c.args) for c in display.create_pen.call_args_list]
        assert palette.GRAY_200 in pens_used  # the value itself
        assert palette.GRAY_600 in pens_used  # the unit, dimmed -- same as the label

    def test_compact_unit_gap_matches_valuetile_exactly(self):
        # ValueTile positions its unit at x + value_width + 4 (relative to
        # the tile's raw left edge, not the value's own draw position at
        # x + theme.padding) -- WeatherTile's compact layout must reproduce
        # that same visual gap, not an extra theme.padding wider.
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        region = _region()  # Region(0, 0, 114, 114)
        tile = WeatherTile(
            region, palette.PenCache(display), "OUTSIDE", unit="F",
            initial_condition="sunny", initial_temperature=79,
        )

        tile.draw(display, theme)

        unit_call = next(c for c in theme.text.call_args_list if c.args[1] == "°F")
        temp_width, _ = theme.measure_text.return_value
        expected_x = region.x + temp_width + 4  # ValueTile's own x + value_width + 4
        assert unit_call.args[2] == expected_x

    def test_wide_unit_gap_matches_valuetile_exactly(self):
        from tmos import Region

        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        region = Region(0, 0, 236, 114)
        tile = WeatherTile(
            region, palette.PenCache(display), "OUTSIDE", unit="F",
            initial_condition="sunny", initial_temperature=79,
        )

        tile.draw(display, theme)

        temp_call = next(c for c in theme.text.call_args_list if c.args[1] == "79")
        unit_call = next(c for c in theme.text.call_args_list if c.args[1] == "°F")
        temp_width, _ = theme.measure_text.return_value
        # Same relative offset from the temperature's own draw position as
        # ValueTile uses from its value's draw position, regardless of
        # what that position is in this (differently laid out) tile.
        assert unit_call.args[2] == temp_call.args[2] + temp_width + 6 - theme.padding

    def test_wide_label_gap_is_ten_pixels_below_the_temperature(self):
        # The project owner asked for 6px more than the prior 4px gap
        # between the temperature and the label in the wide (icon) layout.
        from tmos import Region

        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        region = Region(0, 0, 236, 114)
        tile = WeatherTile(
            region, palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=79,
        )

        tile.draw(display, theme)

        temp_call = next(c for c in theme.text.call_args_list if c.args[1] == "79")
        label_call = next(c for c in theme.text.call_args_list if c.args[1] == "OUTSIDE")
        _, temp_height = theme.measure_text.return_value
        assert label_call.args[3] == temp_call.args[3] + temp_height + 10

    def test_wide_humidity_takes_the_labels_old_row_and_pushes_label_down(self):
        from tmos import Region

        from dashboard import grid

        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        region = Region(0, 0, 236, 114)
        tile = WeatherTile(
            region, palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=79, initial_humidity=62,
        )

        tile.draw(display, theme)

        temp_call = next(c for c in theme.text.call_args_list if c.args[1] == "79")
        humidity_call = next(c for c in theme.text.call_args_list if c.args[1] == "62% HUMIDITY")
        label_call = next(c for c in theme.text.call_args_list if c.args[1] == "OUTSIDE")
        _, temp_height = theme.measure_text.return_value
        grid_step = round(grid.tile_size(480) + theme.padding)

        old_label_y = temp_call.args[3] + temp_height + 10
        assert humidity_call.args[3] == old_label_y  # took the label's old row
        assert humidity_call.args[2] == temp_call.args[2]  # left-aligned with the temperature
        assert label_call.args[3] == old_label_y + grid_step  # pushed down one more row

    def test_wide_humidity_uses_the_same_bright_color_as_the_temperature(self):
        # A plain Mock's create_pen() returns the same object regardless of
        # the rgb it's called with, so pen *identity* can't distinguish
        # colors here -- give it a side_effect that echoes the rgb back,
        # then check the exact sequence of pens set: background, icon
        # (patched out below), temperature, humidity, label.
        from tmos import Region

        display = mock.Mock()
        display.create_pen.side_effect = lambda *rgb: rgb
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        region = Region(0, 0, 236, 114)
        tile = WeatherTile(
            region, palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=79, initial_humidity=62,
        )

        with mock.patch("dashboard.tiles.weather_icon.draw"):
            tile.draw(display, theme)

        set_pen_colors = [c.args[0] for c in display.set_pen.call_args_list]
        assert set_pen_colors == [
            palette.GRAY_900,  # tile background
            palette.GRAY_200,  # temperature
            palette.GRAY_200,  # humidity -- same bright color, not the dimmed label color
            palette.GRAY_600,  # label
        ]

    def test_wide_without_humidity_does_not_draw_it(self):
        from tmos import Region

        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        region = Region(0, 0, 236, 114)
        tile = WeatherTile(
            region, palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=79,
        )

        tile.draw(display, theme)

        rendered = [c.args[1] for c in theme.text.call_args_list]
        assert not any("HUMIDITY" in text for text in rendered)

    def test_compact_ignores_humidity(self):
        # The compact (4x4) layout is deliberately ValueTile-identical and
        # has no equivalent row to insert humidity into.
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        tile = WeatherTile(
            _region(), palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=21.5, initial_humidity=62,
        )

        tile.draw(display, theme)

        rendered = [c.args[1] for c in theme.text.call_args_list]
        assert not any("HUMIDITY" in text for text in rendered)

    def test_icon_pen_is_dimmer_than_the_temperature_text(self):
        # Regression test: the icon used to share GRAY_200 with the
        # temperature/label text and read as "really, really bright"
        # against the tile's dark background -- it should request GRAY_500
        # (a dimmer color) from the pen cache instead.
        from tmos import Region

        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        region = Region(0, 0, 236, 114)
        tile = WeatherTile(
            region, palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=79,
        )

        tile.draw(display, theme)

        pens_used = [tuple(c.args) for c in display.create_pen.call_args_list]
        assert palette.GRAY_500 in pens_used

    def test_compact_tile_draws_no_icon(self):
        # A 4x4 tile (square, 114x114) is not "wide" -- per the project
        # owner's direction, it drops the icon entirely rather than
        # squeezing one in, matching ValueTile's own layout instead.
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        tile = WeatherTile(
            _region(), palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=21.5,
        )

        with mock.patch("dashboard.tiles.weather_icon.draw") as draw:
            tile.draw(display, theme)

        draw.assert_not_called()

    def test_compact_tile_label_sits_at_the_tile_bottom_like_valuetile(self):
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        region = _region()  # Region(0, 0, 114, 114)
        tile = WeatherTile(
            region, palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=21.5,
        )

        tile.draw(display, theme)

        label_call = next(c for c in theme.text.call_args_list if c.args[1] == "OUTSIDE")
        assert label_call.args[2] == region.x + theme.padding
        assert label_call.args[3] == region.y + region.height - theme.padding - 10

    def test_icon_is_drawn_at_half_size_centered_in_its_old_bounding_box(self):
        # A wide (8x4-shaped) tile puts the icon beside the text -- its
        # bounding box is the full height-minus-padding square.
        from tmos import Region

        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        region = Region(0, 0, 236, 114)
        tile = WeatherTile(
            region, palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=21.5,
        )

        with mock.patch("dashboard.tiles.weather_icon.draw") as draw:
            tile.draw(display, theme)

        (_, _, icon_x, icon_y, icon_size, _), _ = draw.call_args
        icon_box_size = region.height - theme.padding * 2
        icon_box_x = region.x + theme.padding
        icon_box_y = region.y + theme.padding

        assert icon_size == int(icon_box_size * 0.5)
        # Centered within the old bounding box, not flush against its edge.
        assert icon_x == icon_box_x + (icon_box_size - icon_size) // 2
        assert icon_y == icon_box_y + (icon_box_size - icon_size) // 2

    def test_wide_tile_label_sits_directly_below_the_temperature_left_aligned(self):
        from tmos import Region

        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        region = Region(0, 0, 236, 114)
        tile = WeatherTile(
            region, palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=21.5,
        )

        tile.draw(display, theme)

        temp_call = next(c for c in theme.text.call_args_list if c.args[1] == "22")
        label_call = next(c for c in theme.text.call_args_list if c.args[1] == "OUTSIDE")

        assert label_call.args[3] > temp_call.args[3]  # sits below the temperature
        assert label_call.args[2] == temp_call.args[2]  # left-aligned with it

    def test_draw_with_unknown_condition_does_not_raise(self):
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        tile = WeatherTile(
            _region(), palette.PenCache(display), "OUTSIDE", initial_condition="not-a-real-condition"
        )

        tile.draw(display, theme)  # should not raise

    def test_wide_tile_with_unknown_condition_does_not_raise(self):
        from tmos import Region

        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        tile = WeatherTile(
            Region(0, 0, 480, 175), palette.PenCache(display), "OUTSIDE",
            initial_condition="not-a-real-condition",
        )

        tile.draw(display, theme)  # should not raise

    def test_draw_with_no_temperature_omits_temperature_text(self):
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        tile = WeatherTile(_region(), palette.PenCache(display), "OUTSIDE", initial_condition="sunny")

        tile.draw(display, theme)

        rendered = [c.args[1] for c in theme.text.call_args_list]
        assert rendered == ["OUTSIDE"]

    def test_wide_tile_uses_horizontal_layout(self):
        # A 16x6 (cols x rows) banner tile is much wider than tall.
        from tmos import Region

        from dashboard import grid

        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        wide_region = Region(0, 0, 480, 175)
        tile = WeatherTile(
            wide_region, palette.PenCache(display), "OUTSIDE",
            initial_condition="sunny", initial_temperature=21.5,
        )

        tile.draw(display, theme)

        temp_call = next(c for c in theme.text.call_args_list if c.args[1] == "22")
        label_call = next(c for c in theme.text.call_args_list if c.args[1] == "OUTSIDE")

        icon_box_size = wide_region.height - theme.padding * 2  # icon's old full-size bounding box
        grid_step = round(grid.tile_size(480) + theme.padding)
        expected_text_x = wide_region.x + theme.padding + icon_box_size + theme.padding
        expected_temp_y = wide_region.y + theme.padding + grid_step

        # Both the temperature and the label share the same left edge, and
        # sit one grid cell down/over from the icon's old (full-size)
        # bounding box -- not flush against the (now smaller) icon.
        assert temp_call.args[2] == expected_text_x
        assert temp_call.args[3] == expected_temp_y
        assert label_call.args[2] == expected_text_x
        assert label_call.args[3] > expected_temp_y  # label sits below the temperature, not beside it
