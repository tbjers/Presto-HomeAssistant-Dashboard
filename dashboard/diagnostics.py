# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Device diagnostics: a per-boot id, reset-cause reporting, and a bridge
from TmOS's message system to the retained MQTT error topic
(dashboard.topics.device_error_topic).

Why a reset-cause report matters here: the device can't publish anything
while it's hung -- but it *can*, on the next boot, say why it restarted. A
watchdog reset (dashboard/watchdog.py) or a hard reset (the physical
button, which is how a hung Presto gets recovered) both land on the error
topic as a "recovered from unexpected reset" message, so an otherwise
invisible hang leaves a trace.

`machine` is import-guarded throughout so this module still imports under
the host test stubs (tests/conftest.py), which don't provide a full
`machine`.
"""

import time

from tmos import MSG_FATAL, MSG_WARNING

from dashboard import topics


def _make_boot_id():
    try:
        import random

        return "{:08x}".format(random.getrandbits(32))
    except (ImportError, AttributeError):
        return "unknown"


# Generated once per import (i.e. once per boot). Stable for the process
# lifetime; lets Node-RED group a boot's errors and detect restarts. A
# repeat across boots is harmless -- the reset-cause report still flags
# that a restart happened.
BOOT_ID = _make_boot_id()


# reset_cause() values that mean "something went wrong" rather than a
# deliberate power-on or soft reboot. "hard" is included: a brownout or a
# press of the physical reset button (the standard way to recover a hung
# device) both report as a hard reset.
UNEXPECTED_RESET_REASONS = ("watchdog", "hard", "unknown")

_RESET_CAUSE_LABELS = (
    ("PWRON_RESET", "power"),
    ("HARD_RESET", "hard"),
    ("WDT_RESET", "watchdog"),
    ("DEEPSLEEP_RESET", "deepsleep"),
    ("SOFT_RESET", "soft"),
)


def reset_reason():
    """
    Returns a short label for the last reset cause -- "power", "hard",
    "watchdog", "deepsleep", "soft" -- or "unknown" if the port reports a
    cause this doesn't recognise, or None if reset-cause info isn't
    available at all (host tests, or a firmware without machine.reset_cause).
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


def describe_unexpected_reset():
    """The reset_reason() label if it indicates an unclean restart worth
    reporting, else None."""
    reason = reset_reason()
    if reason in UNEXPECTED_RESET_REASONS:
        return reason
    return None


def report_boot_reason(mqtt):
    """If the last reset looks unclean, queue a fatal error report for it
    (delivered once MQTT connects). Returns the reason label, or None."""
    reason = describe_unexpected_reset()
    if reason is not None:
        mqtt.report_error(
            topics.ERROR_LEVEL_FATAL,
            "boot",
            "recovered from unexpected reset ({})".format(reason),
        )
    return reason


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
