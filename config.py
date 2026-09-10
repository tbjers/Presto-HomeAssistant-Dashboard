# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
DEVICE_ID + a minimal fallback screen -- NOT the tile/entity registry
itself anymore. The real per-device screens/tiles are published by
Node-RED as a retained JSON message to
dashboard.topics.device_config_topic(DEVICE_ID); see README.md for the
payload contract and an example. dashboard.app.DashboardApp shows
DEFAULT_SCREENS only until that message arrives (which, since MQTT
connects well after boot, is every single boot, briefly -- see
dashboard/app.py's _on_config_update) or if the broker has nothing
retained for this device yet.

DEVICE_ID has to stay local: the device needs it before it can even build
the MQTT topic name to fetch its own config from.

Also holds a couple of purely-local runtime flags (the watchdog settings
below) that aren't worth the validation/UI plumbing of dashboard/settings.py.
"""

from dashboard.grid import STANDARD_SPAN

DEVICE_ID = "presto-office"

# machine.WDT backstop (dashboard/watchdog.py). Set WATCHDOG_ENABLED = False
# before working over USB -- an active WDT can't be stopped without a
# hardware reset and will trip during a slow `mpremote cp` or a REPL pause.
# WATCHDOG_TIMEOUT_MS must stay <= the RP2350 max (~8388ms). Note: if a
# future font choice is re-enabled in dashboard/settings.py and its
# PicoVector .af load blocks longer than this, the WDT would turn that hang
# into a reboot loop -- raise the timeout or gate the feed if so.
WATCHDOG_ENABLED = True
WATCHDOG_TIMEOUT_MS = 8000

DEFAULT_SCREENS = [
    {
        "title": "Dashboard",
        "tiles": [
            {
                "type": "datetime",
                "col": 0, "row": 0, "colspan": 4 * STANDARD_SPAN, "rowspan": STANDARD_SPAN,
            },
        ],
    },
]
