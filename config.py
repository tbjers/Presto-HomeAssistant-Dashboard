# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Declarative tile/entity registry -- non-secret, committed. Single source of
truth for what the dashboard displays and where; dashboard.mqtt_client's
wildcard subscribe means the MQTT subscription list is NOT derived from
this file.

col/row/colspan/rowspan address dashboard.grid's 16-column base grid.
dashboard.grid.STANDARD_SPAN (4) is a "normal" 1-tile-sized tile, matching
compresto's original 114px visual tile proportions.

thresholds use *_SCALE names (3-tuples: background/value-text/
description-text), resolved against dashboard.palette by
dashboard.page._resolve_thresholds -- not single-color names like
"SKY_400", which would resolve to the wrong shape and crash on device.
"""

from dashboard.grid import STANDARD_SPAN

DEVICE_ID = "presto-office"

TILES = [
    {
        # switch.example_switch is a switch entity, not a light -- domain="switch"
        # keeps presto/switch/lamp/{set,state} matching what it actually is
        # (no brightness field in the switch payload shape, unlike light).
        "type": "toggle", "domain": "switch", "slug": "lamp", "label": "LAMP",
        "col": 0, "row": 0, "colspan": STANDARD_SPAN, "rowspan": STANDARD_SPAN,
    },
    {
        "type": "toggle", "domain": "light", "slug": "ceiling", "label": "CEILING", "dimmable": True,
        "col": STANDARD_SPAN, "row": 0, "colspan": STANDARD_SPAN, "rowspan": STANDARD_SPAN,
    },
    {
        "type": "sensor", "domain": "sensor", "slug": "office_temp", "label": "OFFICE", "unit": "C",
        "col": 2 * STANDARD_SPAN, "row": 0, "colspan": STANDARD_SPAN, "rowspan": STANDARD_SPAN,
        "thresholds": [
            (18, "SKY_SCALE"), (25, "GREEN_SCALE"), (28, "AMBER_SCALE"), (None, "ROSE_SCALE"),
        ],
    },
    {
        "type": "scene", "domain": "scene", "slug": "good_night", "label": "GOOD NIGHT",
        "col": 3 * STANDARD_SPAN, "row": 0, "colspan": STANDARD_SPAN, "rowspan": STANDARD_SPAN,
    },
    {
        "type": "datetime",
        "col": 0, "row": STANDARD_SPAN, "colspan": 2 * STANDARD_SPAN, "rowspan": STANDARD_SPAN,
    },
]
