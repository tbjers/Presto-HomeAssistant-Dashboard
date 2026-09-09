"""
Tests for dashboard.diagnostics -- boot id, reset-cause mapping, and the
TmOS-message -> MQTT-error bridge.
"""

import time
from unittest import mock

import pytest

from tmos import MSG_DEBUG, MSG_FATAL, MSG_INFO, MSG_WARNING

from dashboard import diagnostics, topics


class TestBootId:
    def test_is_eight_hex_chars(self):
        assert len(diagnostics.BOOT_ID) == 8
        int(diagnostics.BOOT_ID, 16)  # must parse as hex


class TestResetReason:
    def test_maps_known_causes(self, mock_machine_module):
        mock_machine_module.reset_cause.return_value = mock_machine_module.WDT_RESET
        assert diagnostics.reset_reason() == "watchdog"

        mock_machine_module.reset_cause.return_value = mock_machine_module.PWRON_RESET
        assert diagnostics.reset_reason() == "power"

        mock_machine_module.reset_cause.return_value = mock_machine_module.HARD_RESET
        assert diagnostics.reset_reason() == "hard"

    def test_unrecognised_cause_is_unknown(self, mock_machine_module):
        mock_machine_module.reset_cause.return_value = 999
        assert diagnostics.reset_reason() == "unknown"

    def test_returns_none_when_reset_cause_unavailable(self, mock_machine_module):
        mock_machine_module.reset_cause.side_effect = AttributeError
        assert diagnostics.reset_reason() is None


class TestDescribeUnexpectedReset:
    @pytest.mark.parametrize("cause,expected", [
        ("WDT_RESET", "watchdog"),
        ("HARD_RESET", "hard"),
    ])
    def test_unclean_resets_are_reported(self, mock_machine_module, cause, expected):
        mock_machine_module.reset_cause.return_value = getattr(mock_machine_module, cause)
        assert diagnostics.describe_unexpected_reset() == expected

    @pytest.mark.parametrize("cause", ["PWRON_RESET", "SOFT_RESET", "DEEPSLEEP_RESET"])
    def test_clean_resets_return_none(self, mock_machine_module, cause):
        mock_machine_module.reset_cause.return_value = getattr(mock_machine_module, cause)
        assert diagnostics.describe_unexpected_reset() is None


class TestReportBootReason:
    def test_reports_unclean_reset_as_fatal(self, mock_machine_module):
        mock_machine_module.reset_cause.return_value = mock_machine_module.WDT_RESET
        mqtt = mock.Mock()

        reason = diagnostics.report_boot_reason(mqtt)

        assert reason == "watchdog"
        mqtt.report_error.assert_called_once()
        args = mqtt.report_error.call_args.args
        assert args[0] == topics.ERROR_LEVEL_FATAL
        assert args[1] == "boot"
        assert "watchdog" in args[2]

    def test_clean_reset_reports_nothing(self, mock_machine_module):
        mock_machine_module.reset_cause.return_value = mock_machine_module.PWRON_RESET
        mqtt = mock.Mock()

        assert diagnostics.report_boot_reason(mqtt) is None
        mqtt.report_error.assert_not_called()


class TestDiagnosticsReporter:
    def test_forwards_fatal_as_fatal(self):
        mqtt = mock.Mock()
        reporter = diagnostics.DiagnosticsReporter(mqtt)

        reporter.handle_message("run loop died", MSG_FATAL)

        mqtt.report_error.assert_called_once_with("fatal", "tmos", "run loop died")

    def test_forwards_warning_as_warning(self):
        mqtt = mock.Mock()
        reporter = diagnostics.DiagnosticsReporter(mqtt)

        reporter.handle_message("something odd", MSG_WARNING)

        mqtt.report_error.assert_called_once_with("warning", "tmos", "something odd")

    @pytest.mark.parametrize("severity", [MSG_DEBUG, MSG_INFO])
    def test_ignores_low_severity(self, severity):
        mqtt = mock.Mock()
        reporter = diagnostics.DiagnosticsReporter(mqtt)

        reporter.handle_message("chatter", severity)

        mqtt.report_error.assert_not_called()

    def test_rate_limits_repeated_warnings(self):
        mqtt = mock.Mock()
        reporter = diagnostics.DiagnosticsReporter(mqtt, min_interval_ms=10_000)

        reporter.handle_message("first", MSG_WARNING)
        reporter.handle_message("second", MSG_WARNING)

        assert mqtt.report_error.call_count == 1

    def test_fatal_is_never_rate_limited(self):
        mqtt = mock.Mock()
        reporter = diagnostics.DiagnosticsReporter(mqtt, min_interval_ms=10_000)

        reporter.handle_message("warn", MSG_WARNING)
        reporter.handle_message("fatal now", MSG_FATAL)

        assert mqtt.report_error.call_count == 2

    def test_rate_limit_window_expires(self):
        mqtt = mock.Mock()
        reporter = diagnostics.DiagnosticsReporter(mqtt, min_interval_ms=0)

        reporter.handle_message("first", MSG_WARNING)
        time.sleep(0.001)
        reporter.handle_message("second", MSG_WARNING)

        assert mqtt.report_error.call_count == 2
