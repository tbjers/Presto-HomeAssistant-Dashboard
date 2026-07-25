"""
One-off connectivity probe: connects to the EMQX broker using secrets.py,
subscribes to presto/+/+/state, and prints anything received within a short
window. Run via `mpremote run scripts/mqtt_smoke_test.py` -- does not touch
flash/main.py. Useful for isolating "does the device actually receive
retained messages at the MQTT layer" from "does DashboardPage/state_store
wiring work", since main.py's os.boot(run=True) blocks the REPL and can't
be probed live while it's running.
"""

import time

import secrets
from umqtt.simple import MQTTClient


def on_message(topic, msg):
    print("RECEIVED", topic, msg)


client = MQTTClient(
    "presto-mqtt-smoke-test",
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

client.subscribe(b"presto/+/+/state")
print("subscribed to presto/+/+/state, polling for 10s...")

deadline = time.ticks_add(time.ticks_ms(), 10000)
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    client.check_msg()
    time.sleep_ms(200)

print("done polling")
client.disconnect()
