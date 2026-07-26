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
"""

from dashboard.grid import STANDARD_SPAN

DEVICE_ID = "presto-office"

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
