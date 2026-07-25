"""
Template for secrets.py (gitignored — never commit real values).

Copy this file to secrets.py and fill in real values. WIFI_SSID/WIFI_PASSWORD
match Pimoroni's own Presto firmware convention (presto.connect() reads these
directly) — do not rename them.

If the device already has a secrets.py from prior experimentation (e.g. with
WIFI_SSID/WIFI_PASSWORD already set), add the MQTT_* fields to that existing
file rather than overwriting it with this template.
"""

WIFI_SSID = "..."
WIFI_PASSWORD = "..."

MQTT_HOST = "..."
MQTT_PORT = 1883
MQTT_USER = "..."
MQTT_PASSWORD = "..."
