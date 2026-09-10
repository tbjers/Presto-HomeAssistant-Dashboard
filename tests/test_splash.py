"""
Tests for dashboard.splash.show().

Can't verify pixels land in the right place on desktop CPython (no real
PicoGraphics rasterizer -- see tests/conftest.py's stubs), but can verify the
drawing calls happen in the right shape: the screen gets cleared, the logo is
blitted as merged-run rectangles (one call per contiguous ink run per row,
per color plane -- see dashboard/logo.py and dashboard/splash.py's
_draw_plane), the label is drawn, and the display is flipped exactly once at
the end. Logo/label rendering was confirmed visually correct via
`mpremote run` against real hardware when this was added.
"""

from types import SimpleNamespace
from unittest import mock

import pytest

from tmos import MSG_DEBUG, MSG_FATAL, MSG_INFO

from dashboard import splash
from dashboard.splash import show


@pytest.fixture(autouse=True)
def _reset_splash_state():
    splash._ctx = None
    splash._boot_messages_active = False
    yield


def _os(mock_presto_module):
    display = mock_presto_module.Presto.return_value.display
    display.reset_mock()
    display.get_bounds.return_value = (480, 480)
    display.create_pen.side_effect = lambda *rgb: rgb

    return SimpleNamespace(display=display, update_display=mock.Mock())


class TestShow:
    def test_clears_and_flips_display_once(self, mock_presto_module):
        os_ = _os(mock_presto_module)
        show(os_)

        os_.display.clear.assert_called_once()
        os_.update_display.assert_called_once_with()

    def test_draws_label_text(self, mock_presto_module):
        # font5x5 is rendered via display.rectangle(), not display.text() --
        # see dashboard/font.py. A non-trivial rect count is evidence glyphs
        # were actually blitted (in addition to the logo's own rectangles).
        os_ = _os(mock_presto_module)
        show(os_)

        assert os_.display.rectangle.call_count > 10

    def test_draws_logo_planes(self, mock_presto_module):
        from dashboard.logo import BLUE, BLUE_ROWS, WHITE_ROWS

        os_ = _os(mock_presto_module)
        show(os_)

        os_.display.create_pen.assert_any_call(*BLUE)

        def run_count(rows):
            count = 0
            width = 32
            for bits in rows:
                col = 0
                in_run = False
                while col < width:
                    lit = bool(bits & (1 << (width - 1 - col)))
                    if lit and not in_run:
                        count += 1
                    in_run = lit
                    col += 1
            return count

        expected_runs = run_count(BLUE_ROWS) + run_count(WHITE_ROWS)
        # Some rectangle() calls are the label's glyphs, not the logo -- just
        # assert there are at least as many as the logo alone requires.
        assert os_.display.rectangle.call_count >= expected_runs


class TestSetStatus:
    def test_noop_before_show(self, mock_presto_module):
        os_ = _os(mock_presto_module)

        splash.set_status(os_, "Connecting")

        os_.update_display.assert_not_called()
        os_.display.rectangle.assert_not_called()

    def test_redraws_strip_and_flips(self, mock_presto_module):
        os_ = _os(mock_presto_module)
        show(os_)
        os_.display.reset_mock()
        os_.update_display.reset_mock()

        splash.set_status(os_, "Connecting Wi-Fi")

        # one strip-clear rectangle + the glyph rectangles
        assert os_.display.rectangle.call_count > 1
        os_.update_display.assert_called_once_with()


class TestBootMessageHandler:
    def test_forwards_info_messages_to_status(self, mock_presto_module):
        os_ = _os(mock_presto_module)
        show(os_)
        handler = splash.boot_message_handler(os_)
        with mock.patch.object(splash, "set_status") as set_status:
            handler("Connecting to WiFI", MSG_INFO)
            set_status.assert_called_once_with(os_, "Connecting to WiFI")

    def test_ignores_debug_messages(self, mock_presto_module):
        os_ = _os(mock_presto_module)
        show(os_)
        handler = splash.boot_message_handler(os_)
        with mock.patch.object(splash, "set_status") as set_status:
            handler("Added task: ...", MSG_DEBUG)
            set_status.assert_not_called()

    def test_goes_inert_once_run_loop_starts(self, mock_presto_module):
        os_ = _os(mock_presto_module)
        show(os_)
        handler = splash.boot_message_handler(os_)
        with mock.patch.object(splash, "set_status") as set_status:
            handler("Starting tasks", MSG_INFO)
            handler("some later message", MSG_INFO)
            handler("a fatal one", MSG_FATAL)
            set_status.assert_not_called()
