"""
DashboardApp(App) -- top-level TmOS App wiring DashboardState, DashboardMQTT,
and DashboardPage together. See dashboard.page for why DashboardPage isn't a
StaticPage, and dashboard.mqtt_client for the connection lifecycle design.
"""

from tmos_apps import App

from dashboard.mqtt_client import DashboardMQTT
from dashboard.page import DashboardPage
from dashboard.state_store import DashboardState
from dashboard.tz import eastern_utc_offset


class DashboardApp(App):
    name = "Dashboard"

    def __init__(self, config, secrets):
        self._config = config
        self._secrets = secrets
        self._state = DashboardState()
        self._mqtt = None
        self._page = None
        self._os = None

    def setup(self, window_manager):
        self._os = window_manager.os
        self._mqtt = DashboardMQTT(
            self._state,
            device_id=self._config.DEVICE_ID,
            host=self._secrets.MQTT_HOST,
            port=getattr(self._secrets, "MQTT_PORT", 1883),
            user=getattr(self._secrets, "MQTT_USER", None),
            password=getattr(self._secrets, "MQTT_PASSWORD", None),
        )
        self._page = DashboardPage(self._config.TILES, self._state, self._mqtt)

    def pages(self):
        return [self._page]

    def tasks(self):
        return [
            App.Task(self._mqtt.tick, execution_frequency=10, touch_forces_execution=False),
            App.Task(self._update_timezone, execution_frequency=1 / 60, touch_forces_execution=False),
        ]

    def _update_timezone(self):
        # Re-evaluated every ~minute (cheap: no I/O) so a device left
        # running across a DST transition picks up the new offset
        # without a reboot -- see dashboard/tz.py.
        self._os.utc_offset = eastern_utc_offset()
