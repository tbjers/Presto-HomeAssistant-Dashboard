# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
machine.WDT feeder -- the last-resort backstop for the idle hang.

The real fix for the hang is in dashboard/mqtt_client.py (bounded socket
reads + keepalive pings). This just ensures that *any* future freeze of
the single cooperative run loop -- from any cause -- reboots the device on
its own instead of needing someone to hold the reset button.

Wiring (main.py): registered with os.add_task(), NOT as one of
DashboardApp's App.Tasks. App tasks are torn down whenever the current app
changes (tmos_apps.AppManager.set_current_app), so a WDT feed living there
would stop being fed the moment the user opened the Settings app -> a
spurious reboot a few seconds later.

Arming is deferred to the first tick() rather than done at construction:
os.boot() blocks synchronously on Wi-Fi association and NTP
(ntptime.timeout = 10s in main.py), either of which can exceed the
RP2350's ~8.3s max WDT period. By the time tick() first runs, the run loop
is turning and boot is done.

Once started, machine.WDT cannot be stopped or reconfigured until a
hardware reset. Set config.WATCHDOG_ENABLED = False to keep it off while
iterating over USB (a slow `mpremote cp`, or sitting at the REPL, will
otherwise trip it).
"""


class WatchdogFeeder:
    def __init__(self, timeout_ms):
        self._timeout_ms = timeout_ms
        self._wdt = None

    def tick(self):
        if self._wdt is None:
            from machine import WDT

            self._wdt = WDT(timeout=self._timeout_ms)
        self._wdt.feed()
