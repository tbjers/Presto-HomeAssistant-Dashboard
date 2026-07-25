"""
Template for secrets.py (gitignored — never commit real values).

Copy this file to secrets.py and fill in real values. WIFI_SSID/WIFI_PASSWORD
match Pimoroni's own Presto firmware convention (presto.connect() reads these
directly) — do not rename them.

Note: this device already has a working secrets.py from prior TmOS
experimentation with WIFI_SSID/WIFI_PASSWORD set. Add the MQTT_* fields to
that existing file rather than overwriting it — don't blindly `mpremote cp`
this template's real device.
"""

WIFI_SSID = "..."
WIFI_PASSWORD = "..."

MQTT_HOST = "..."
MQTT_PORT = 1883
MQTT_USER = "..."
MQTT_PASSWORD = "..."
