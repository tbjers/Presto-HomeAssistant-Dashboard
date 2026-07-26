# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
One-off probe: connects wifi (via tmos.OS.boot, no run loop), connects to
the real broker (secrets.py), subscribes to this device's own config topic
(dashboard.topics.device_config_topic(config.DEVICE_ID)), and prints
whatever arrives, run through the real dashboard.topics.parse_config_payload
-- to confirm Node-RED's actual published config round-trips through the
real MQTT/parsing pipeline on real hardware. Run via
`mpremote run scripts/config_topic_smoke_test.py` -- does not touch
flash/main.py, mirrors scripts/mqtt_smoke_test.py's isolation approach.
"""

import time

from tmos import OS

import config
import secrets
from umqtt.simple import MQTTClient

from dashboard import topics

print("connecting wifi...")
os = OS(layers=1, full_res=True)
os.boot(wifi=True, use_ntp=False, run=False)
print("wifi connected")

received = []


def on_message(topic, msg):
    received.append((topic, msg))
    print("RAW", topic, msg)
    payload = topics.parse_config_payload(msg)
    if payload is None:
        print("  -> REJECTED by parse_config_payload (see dashboard/topics.py for why)")
        return
    print("  -> ACCEPTED:", len(payload["screens"]), "screen(s)")
    for screen in payload["screens"]:
        print("     -", screen.get("title"), "-", len(screen["tiles"]), "tile(s)")


client = MQTTClient(
    "presto-config-smoke-test",
    secrets.MQTT_HOST,
    port=getattr(secrets, "MQTT_PORT", 1883),
    user=getattr(secrets, "MQTT_USER", None),
    password=getattr(secrets, "MQTT_PASSWORD", None),
    keepalive=60,
)
client.set_callback(on_message)

print("connecting to", secrets.MQTT_HOST, "...")
client.connect(timeout=5)
print("connected")

topic = topics.device_config_topic(config.DEVICE_ID)
client.subscribe(topic.encode())
print("subscribed to", topic, "-- polling for 10s...")

deadline = time.ticks_add(time.ticks_ms(), 10000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    client.check_msg()
    time.sleep_ms(200)

print("done polling;", len(received), "message(s) received")
client.disconnect()
