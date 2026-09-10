# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Device diagnostics: a per-boot id, a "was the last session a hang?" check,
and a bridge from TmOS's message system to the retained MQTT error topic
(dashboard.topics.device_error_topic).

Why this can't just read machine.reset_cause(): on the RP2350 that call is
effectively binary -- "watchdog-caused" vs "power-on" -- and *every*
software reboot goes through the watchdog (machine.reset(), mpremote's
soft reset, and a real WDT timeout all report WDT_RESET), while the
physical reset button reports as a plain power-on. Confirmed on hardware.
So reset_cause is kept only as payload context; the actual hang signal is
**how long the previous session ran**. A reflash or a settings reboot has
a previous uptime of seconds-to-minutes; a hang has hours.

Mechanism: init_boot_state() reads a one-line breadcrumb file left by the
previous boot, then overwrites it with "not a long run yet". A periodic
task (mark_long_run_if_due) flips the breadcrumb to "long run" once the
current session passes LONG_RUN_THRESHOLD_MS, refreshing the recorded
uptime hourly after that. On the next boot, report_boot_reason() sees a
"long run" breadcrumb and reports it as a fatal error -- an
otherwise-invisible hang (the device can't publish while frozen) leaves a
trace once the watchdog reboots it.

`machine` is import-guarded so this still imports under the host test
stubs (tests/conftest.py).
"""

import json
import time

from tmos import MSG_FATAL, MSG_WARNING

from dashboard import topics

_BREADCRUMB_PATH = "diag_state.json"

# A session that runs past this is "long" -- longer than any reflash /
# settings-reboot cycle, so a reset after this point is a candidate hang.
LONG_RUN_THRESHOLD_MS = 600_000  # 10 minutes
# Once "long", rewrite the recorded uptime this often so the reported
# figure reflects an 8-hour session, not a flat 10 minutes. ~24
# writes/day is negligible flash wear.
LONG_RUN_REFRESH_MS = 3_600_000  # 1 hour


def _make_boot_id():
    try:
        import random

        return "{:08x}".format(random.getrandbits(32))
    except (ImportError, AttributeError):
        return "unknown"


# Generated once per import (i.e. once per boot). Lets Node-RED group a
# boot's errors; a repeat across boots is harmless.
BOOT_ID = _make_boot_id()


_RESET_CAUSE_LABELS = (
    ("PWRON_RESET", "power"),
    ("HARD_RESET", "hard"),
    ("WDT_RESET", "watchdog"),
    ("DEEPSLEEP_RESET", "deepsleep"),
    ("SOFT_RESET", "soft"),
)


def reset_reason():
    """
    Short label for the last reset cause -- "power", "watchdog", etc, or
    "unknown" for an unrecognised code, or None if unavailable (host
    tests, or a firmware without machine.reset_cause). On the RP2350 this
    only ever meaningfully distinguishes "watchdog" (any software reboot,
    hang included) from "power" (cold boot or the reset button) -- see the
    module docstring. Payload context only; not a trigger.
    """
    try:
        import machine
    except ImportError:
        return None
    try:
        cause = machine.reset_cause()
    except (AttributeError, NotImplementedError, OSError):
        return None
    for attr, label in _RESET_CAUSE_LABELS:
        if getattr(machine, attr, None) == cause:
            return label
    return "unknown"


# --- previous/current session breadcrumb --------------------------------

_path = _BREADCRUMB_PATH
_previous_run = None
_boot_ticks = None
_long_run_written = False
_next_long_run_write_ms = 0


def _read_state(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_state(data):
    try:
        with open(_path, "w") as f:
            json.dump(data, f)
    except OSError:
        pass


def init_boot_state(path=None):
    """Read the previous boot's breadcrumb (available afterwards via
    previous_run()), then reset it for this session. Call once at
    startup, before report_boot_reason()."""
    global _path, _previous_run, _boot_ticks, _long_run_written, _next_long_run_write_ms
    if path is not None:
        _path = path
    _boot_ticks = time.ticks_ms()
    _long_run_written = False
    _next_long_run_write_ms = 0
    _previous_run = _read_state(_path)
    _write_state({"long_run": False})


def previous_run():
    """The previous boot's breadcrumb dict, or None. Populated by
    init_boot_state()."""
    return _previous_run


def mark_long_run_if_due():
    """Task fn: once this session passes LONG_RUN_THRESHOLD_MS, record it
    (and refresh the uptime hourly) so the next boot can tell a hang from
    a routine restart."""
    global _long_run_written, _next_long_run_write_ms
    if _boot_ticks is None:
        return
    now = time.ticks_ms()
    uptime_ms = time.ticks_diff(now, _boot_ticks)
    if uptime_ms < LONG_RUN_THRESHOLD_MS:
        return
    if _long_run_written and time.ticks_diff(now, _next_long_run_write_ms) < 0:
        return
    _write_state({"long_run": True, "uptime_s": uptime_ms // 1000})
    _long_run_written = True
    _next_long_run_write_ms = time.ticks_add(now, LONG_RUN_REFRESH_MS)


def report_boot_reason(mqtt):
    """If the previous session ran long enough to have been a hang, queue
    a fatal error report for it (delivered once MQTT connects). Returns
    the previous uptime in seconds if reported, else None."""
    prev = _previous_run
    if not prev or not prev.get("long_run"):
        return None
    uptime = prev.get("uptime_s")
    mqtt.report_error(
        topics.ERROR_LEVEL_FATAL,
        "boot",
        "previous session ran ~{}s then reset (reset_cause={})".format(uptime, reset_reason()),
    )
    return uptime


class DiagnosticsReporter:
    """
    Forwards TmOS messages at or above `min_severity` to
    DashboardMQTT.report_error. Register handle_message via
    os.add_message_handler.

    Lower-severity messages are rate-limited (`min_interval_ms`) so a
    flapping subsystem can't spam the error topic; MSG_FATAL always gets
    through, since the run loop posts exactly one on its way down
    (tmos.py:446) and that's the message you most want.
    """

    def __init__(self, mqtt, min_severity=MSG_WARNING, min_interval_ms=5000):
        self._mqtt = mqtt
        self._min_severity = min_severity
        self._min_interval_ms = min_interval_ms
        self._last_sent_at = None

    def handle_message(self, message, severity):
        if severity < self._min_severity:
            return
        now = time.ticks_ms()
        if (
            severity < MSG_FATAL
            and self._last_sent_at is not None
            and time.ticks_diff(now, self._last_sent_at) < self._min_interval_ms
        ):
            return
        self._last_sent_at = now
        level = topics.ERROR_LEVEL_FATAL if severity >= MSG_FATAL else topics.ERROR_LEVEL_WARNING
        self._mqtt.report_error(level, "tmos", str(message))
