"""
Hardware stubs, adapted from TmOS's own tests/conftest.py, so dashboard
code (and TmOS itself) can be imported and unit tested on desktop Python.
"""

import sys
import time

from unittest import mock

import pytest

# Stub the Presto platform imports so we can test business logic on
# desktop hardware.

mock_presto = type(sys)("presto")
mock_presto.Presto = mock.Mock()
mock_presto.Presto.return_value.connect = mock.Mock()
mock_presto.Presto.return_value.set_led_rgb = mock.Mock()
mock_presto.Buzzer = mock.Mock()
sys.modules["presto"] = mock_presto

mock_ntptime = type(sys)("ntptime")
mock_ntptime.settime = mock.Mock()
sys.modules["ntptime"] = mock_ntptime

mock_picographics = type(sys)("picographics")
mock_picographics.PicoGraphics = mock.create_autospec(object, instance=False)
mock_picographics.PicoGraphics.return_value.set_pen = mock.Mock()
mock_picographics.PicoGraphics.return_value.create_pen = mock.Mock()
mock_picographics.PicoGraphics.return_value.set_font = mock.Mock()
mock_picographics.PicoGraphics.return_value.rectangle = mock.Mock()
mock_picographics.PicoGraphics.return_value.line = mock.Mock()
mock_picographics.PicoGraphics.return_value.text = mock.Mock()
mock_picographics.PicoGraphics.return_value.set_clip = mock.Mock()
mock_picographics.PicoGraphics.return_value.remove_clip = mock.Mock()
mock_picographics.PicoGraphics.return_value.get_bounds = mock.Mock()
mock_picographics.PicoGraphics.return_value.get_bounds.return_value = (480, 480)
mock_picographics.PicoGraphics.return_value.measure_text = mock.Mock()
mock_picographics.PicoGraphics.return_value.measure_text.return_value = 50
sys.modules["picographics"] = mock_picographics
mock_presto.Presto.return_value.display = mock_picographics.PicoGraphics.return_value

mock_picovector = type(sys)("picovector")
mock_picovector.PicoVector = mock.create_autospec(object, instance=False)
mock_picovector.PicoVector.return_value.set_font = mock.Mock()
mock_picovector.PicoVector.return_value.set_font_line_height = mock.Mock()
mock_picovector.PicoVector.return_value.set_transform = mock.Mock()
mock_picovector.PicoVector.return_value.set_antialiasing = mock.Mock()
mock_picovector.Transform = mock.create_autospec(object, instance=False)
mock_picovector.ANTIALIAS_BEST = mock.Mock()
sys.modules["picovector"] = mock_picovector

# Needed for typing; not the object within a presto instance (that's a
# generic recursive mock from the Presto definition above).
mock_touch = type(sys)("touch")
mock_touch.FT6236 = mock.create_autospec(object, instance=False)
mock_touch.FT6236.return_value.state = False
mock_touch.FT6236.return_value.state2 = False
mock_touch.FT6236.return_value.poll = mock.Mock()
sys.modules["touch"] = mock_touch
mock_presto.Presto.return_value.touch = mock_touch.FT6236.return_value

time.ticks_ms = lambda: time.monotonic_ns() // 1_000_000
time.ticks_us = lambda: time.monotonic_ns() // 1000
time.ticks_diff = lambda a, b: a - b
time.sleep_ms = lambda s: time.sleep(s / 1000)

sys.print_exception = mock.Mock()


@pytest.fixture
def mock_presto_module():
    """Supplies the mock/stub used for the "presto" module. Reset per test."""
    mock_presto.Presto.reset_mock()
    mock_presto.Buzzer.reset_mock()
    return mock_presto


@pytest.fixture
def mock_ntptime_module():
    """Supplies the mock/stub used for the "ntptime" module. Reset per test."""
    mock_ntptime.settime.reset_mock()
    return mock_ntptime


@pytest.fixture
def mock_touch_factory():
    """Provides a mock touch data structure matching TmOS's expected shape."""

    class State:
        state = False
        x = 0
        y = 0
        state2 = False
        x2 = 0
        y2 = 0

    return State
