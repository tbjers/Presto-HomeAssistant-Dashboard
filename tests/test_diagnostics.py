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


class TestInitBootState:
    def test_reads_previous_breadcrumb_then_resets_it(self, tmp_path):
        path = tmp_path / "diag_state.json"
        path.write_text('{"long_run": true, "uptime_s": 7200}')

        diagnostics.init_boot_state(str(path))

        assert diagnostics.previous_run() == {"long_run": True, "uptime_s": 7200}
        # file is reset for this session
        import json as _json

        assert _json.loads(path.read_text()) == {"long_run": False}

    def test_missing_breadcrumb_is_fine(self, tmp_path):
        path = tmp_path / "nope.json"

        diagnostics.init_boot_state(str(path))

        assert diagnostics.previous_run() is None
        assert path.exists()  # freshly written

    def test_corrupt_breadcrumb_is_fine(self, tmp_path):
        path = tmp_path / "diag_state.json"
        path.write_text("{not json")

        diagnostics.init_boot_state(str(path))

        assert diagnostics.previous_run() is None


class TestMarkLongRunIfDue:
    def test_noop_before_threshold(self, tmp_path):
        path = tmp_path / "diag_state.json"
        diagnostics.init_boot_state(str(path))

        diagnostics.mark_long_run_if_due()

        import json as _json

        assert _json.loads(path.read_text()) == {"long_run": False}

    def test_writes_long_run_once_threshold_passed(self, tmp_path):
        path = tmp_path / "diag_state.json"
        diagnostics.init_boot_state(str(path))
        # simulate ~2h of uptime
        diagnostics._boot_ticks = time.ticks_add(time.ticks_ms(), -7_200_000)

        diagnostics.mark_long_run_if_due()

        import json as _json

        state = _json.loads(path.read_text())
        assert state["long_run"] is True
        assert state["uptime_s"] >= 7_000

    def test_does_not_rewrite_every_call(self, tmp_path):
        path = tmp_path / "diag_state.json"
        diagnostics.init_boot_state(str(path))
        diagnostics._boot_ticks = time.ticks_add(time.ticks_ms(), -700_000)

        diagnostics.mark_long_run_if_due()
        first = path.read_text()
        diagnostics._boot_ticks = time.ticks_add(time.ticks_ms(), -900_000)
        diagnostics.mark_long_run_if_due()

        assert path.read_text() == first  # refresh interval not elapsed


class TestReportBootReason:
    def test_reports_long_previous_run_as_fatal(self, mock_machine_module):
        mock_machine_module.reset_cause.return_value = mock_machine_module.WDT_RESET
        diagnostics._previous_run = {"long_run": True, "uptime_s": 28800}
        mqtt = mock.Mock()

        uptime = diagnostics.report_boot_reason(mqtt)

        assert uptime == 28800
        args = mqtt.report_error.call_args.args
        assert args[0] == topics.ERROR_LEVEL_FATAL
        assert args[1] == "boot"
        assert "28800" in args[2]
        assert "watchdog" in args[2]  # reset_cause carried as context

    def test_short_previous_run_reports_nothing(self):
        diagnostics._previous_run = {"long_run": False}
        mqtt = mock.Mock()

        assert diagnostics.report_boot_reason(mqtt) is None
        mqtt.report_error.assert_not_called()

    def test_no_previous_run_reports_nothing(self):
        diagnostics._previous_run = None
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
