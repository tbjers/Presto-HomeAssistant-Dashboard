"""
Tests for dashboard.palette colors, PenCache, and threshold selection.
"""

from unittest import mock

import pytest

from dashboard import palette
from dashboard.palette import PenCache, color_for_thresholds


def test_color_constants_match_compresto_exactly():
    # Spot-check a representative sample against compresto's ui.py values.
    assert palette.GRAY_950 == (10, 10, 10)
    assert palette.GRAY_900 == (23, 23, 23)
    assert palette.GRAY_200 == (229, 229, 229)
    assert palette.GREEN_400 == (74, 222, 128)
    assert palette.ROSE_600 == (225, 29, 72)
    assert palette.SKY_400 == (56, 189, 248)
    assert palette.AMBER_400 == (251, 191, 36)
    assert palette.PURPLE_600 == (147, 51, 234)
    assert palette.WHITE == (255, 255, 255)
    assert palette.BLACK == (0, 0, 0)


class TestPenCache:
    def test_creates_pen_on_first_request(self):
        display = mock.Mock()
        display.create_pen.return_value = 42
        cache = PenCache(display)

        pen = cache.get((10, 20, 30))

        display.create_pen.assert_called_once_with(10, 20, 30)
        assert pen == 42

    def test_caches_pen_for_repeated_rgb(self):
        display = mock.Mock()
        display.create_pen.return_value = 42
        cache = PenCache(display)

        cache.get((10, 20, 30))
        cache.get((10, 20, 30))

        display.create_pen.assert_called_once_with(10, 20, 30)

    def test_creates_distinct_pens_for_distinct_rgb(self):
        display = mock.Mock()
        display.create_pen.side_effect = [1, 2]
        cache = PenCache(display)

        pen_a = cache.get((10, 20, 30))
        pen_b = cache.get((40, 50, 60))

        assert (pen_a, pen_b) == (1, 2)
        assert display.create_pen.call_count == 2


class TestColorForThresholds:
    THRESHOLDS = [
        (18, palette.SKY_400),
        (25, palette.GREEN_400),
        (28, palette.AMBER_400),
        (None, palette.ROSE_400),
    ]

    def test_returns_default_when_value_is_none(self):
        assert color_for_thresholds(None, self.THRESHOLDS, default="fallback") == "fallback"

    @pytest.mark.parametrize(
        "value,expected",
        [
            (0, palette.SKY_400),
            (17.9, palette.SKY_400),
            (18, palette.GREEN_400),  # upper bound is exclusive
            (20, palette.GREEN_400),
            (24.9, palette.GREEN_400),
            (25, palette.AMBER_400),
            (27.9, palette.AMBER_400),
            (28, palette.ROSE_400),
            (100, palette.ROSE_400),
        ],
    )
    def test_matches_compresto_temperature_scale(self, value, expected):
        assert color_for_thresholds(value, self.THRESHOLDS) == expected
