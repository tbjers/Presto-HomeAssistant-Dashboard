"""
Tests for dashboard.weather_icons (data-shape sanity, mirroring
tests/test_icons.py) and dashboard.weather_icon (the renderer).
"""

from array import array
from unittest import mock

from dashboard import weather_icon
from dashboard.weather_icons import FIXED_POINT_SCALE, VIEWBOX, WEATHER_ICONS

# The full set of Home Assistant weather.* condition states (verified
# against HA's weather integration docs) -- every one must have an icon,
# with no KeyError fallback needed for a real HA condition string.
ALL_HA_CONDITIONS = (
    "clear-night", "cloudy", "exceptional", "fog", "hail", "lightning",
    "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy", "snowy-rainy",
    "sunny", "windy", "windy-variant",
)


class TestWeatherIconsData:
    def test_covers_every_ha_condition(self):
        assert set(WEATHER_ICONS.keys()) == set(ALL_HA_CONDITIONS)

    def test_every_condition_has_at_least_one_subpath(self):
        for condition, (lengths, data) in WEATHER_ICONS.items():
            assert len(lengths) > 0, condition

    def test_data_length_matches_the_declared_point_counts(self):
        # Each point is 2 uint16s (x, y) -- 4 bytes -- so data's byte length
        # must be exactly 4 * sum(lengths).
        for condition, (lengths, data) in WEATHER_ICONS.items():
            assert len(data) == sum(lengths) * 4, condition

    def test_every_decoded_point_is_within_the_scaled_viewbox(self):
        for condition, (lengths, data) in WEATHER_ICONS.items():
            coords = array("H", data)
            for value in coords:
                assert 0 <= value <= VIEWBOX * FIXED_POINT_SCALE, condition

    def test_cloudy_fallback_condition_exists(self):
        # dashboard.weather_icon falls back to this for an unknown condition.
        assert "cloudy" in WEATHER_ICONS


class TestWeatherIconDraw:
    def test_draws_with_the_given_pen(self):
        display = mock.Mock()
        weather_icon.draw(display, "sunny", 0, 0, 48, pen=42)
        display.set_pen.assert_called_with(42)

    def test_unknown_condition_falls_back_to_cloudy_without_raising(self):
        display = mock.Mock()
        weather_icon.draw(display, "not-a-real-condition", 0, 0, 48, pen=1)  # should not raise

    def test_none_condition_falls_back_to_cloudy_without_raising(self):
        display = mock.Mock()
        weather_icon.draw(display, None, 0, 0, 48, pen=1)  # should not raise

    def test_every_ha_condition_draws_without_raising(self):
        display = mock.Mock()
        for condition in ALL_HA_CONDITIONS:
            weather_icon.draw(display, condition, 0, 0, 48, pen=1)
