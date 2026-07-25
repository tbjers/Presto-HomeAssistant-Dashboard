"""
Tests for dashboard.splash.show().

Can't verify pixels land in the right place on desktop CPython (no real
PicoGraphics/PicoVector rasterizer -- see tests/conftest.py's stubs), but
can verify the drawing calls happen in the right shape: the screen gets
cleared, the icon polygon is built from all of
icons.HOME_ASSISTANT_OUTLINE plus one circle per icons.HOME_ASSISTANT_DOTS
entry, the label is drawn, and the display is flipped exactly once at the
end. Confirmed visually correct (icon shape, label fit, backlight-on by
default, no crash from a second concurrent PicoVector instance once
Theme.setup() creates its own) via `mpremote run` against real hardware
when this was added.
"""

from types import SimpleNamespace
from unittest import mock

import picovector

from dashboard.icons import HOME_ASSISTANT_DOTS, HOME_ASSISTANT_OUTLINE
from dashboard.splash import _LABEL, show


def _os(mock_presto_module):
    display = mock_presto_module.Presto.return_value.display
    display.reset_mock()
    display.get_bounds.return_value = (480, 480)
    display.create_pen.side_effect = lambda *rgb: rgb
    display.measure_text.return_value = 120

    # Polygon()/PicoVector() are Mock classes shared across the whole test
    # session (see tests/conftest.py) -- reset their recorded calls so
    # assertions here don't pick up state from other tests.
    picovector.Polygon.reset_mock()
    picovector.Polygon.return_value.reset_mock()
    picovector.PicoVector.reset_mock()
    picovector.PicoVector.return_value.reset_mock()

    return SimpleNamespace(display=display, update_display=mock.Mock())


class TestShow:
    def test_clears_and_flips_display_once(self, mock_presto_module):
        os_ = _os(mock_presto_module)
        show(os_)

        os_.display.clear.assert_called_once()
        os_.update_display.assert_called_once_with()

    def test_draws_label_text(self, mock_presto_module):
        os_ = _os(mock_presto_module)
        show(os_)

        texts = [call.args[0] for call in os_.display.text.call_args_list]
        assert _LABEL in texts

    def test_builds_icon_from_outline_and_dots(self, mock_presto_module):
        os_ = _os(mock_presto_module)
        show(os_)

        vector = picovector.PicoVector.return_value
        polygon = picovector.Polygon.return_value

        assert len(polygon.path.call_args.args) == len(HOME_ASSISTANT_OUTLINE)
        assert polygon.circle.call_count == len(HOME_ASSISTANT_DOTS)
        vector.draw.assert_called_once_with(polygon)
