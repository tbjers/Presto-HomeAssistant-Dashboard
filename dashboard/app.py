# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

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
        self._pages = []
        self._os = None
        self._window_manager = None
        self._applied_config = None

    def setup(self, window_manager):
        self._os = window_manager.os
        self._window_manager = window_manager
        self._mqtt = DashboardMQTT(
            self._state,
            device_id=self._config.DEVICE_ID,
            host=self._secrets.MQTT_HOST,
            port=getattr(self._secrets, "MQTT_PORT", 1883),
            user=getattr(self._secrets, "MQTT_USER", None),
            password=getattr(self._secrets, "MQTT_PASSWORD", None),
        )
        self._pages = self._build_pages(self._config.DEFAULT_SCREENS)
        self._state.on_update("device/config", self._on_config_update)

    def pages(self):
        # Force a fresh setup() on every call, not just the first: this app
        # reuses the same DashboardPage instances across app switches
        # (tmos_apps.AppManager.set_current_app() calls pages() every time
        # it's made current again), and WindowManager.remove_page()
        # (tmos_ui.py) calls page.teardown() when switching away -- which
        # wipes DashboardPage._plain_tiles/_controls (dashboard/page.py) --
        # but nothing in vendored code ever resets page.needs_setup back to
        # True afterward, so setup() would otherwise never rerun to rebuild
        # them, leaving a page that's permanently blank after the first
        # switch away and back. Confirmed on real hardware: Dashboard ->
        # Settings -> Dashboard left only the systray visible.
        for page in self._pages:
            page.needs_setup = True
        return self._pages

    def _build_pages(self, screens):
        return [
            DashboardPage(screen.get("title", "Dashboard"), screen["tiles"], self._state, self._mqtt)
            for screen in screens
        ]

    def _on_config_update(self, payload):
        # DashboardApp.pages() is pulled once at boot, before Wi-Fi/MQTT
        # even connect (see main.py's AppManager.add_app call) -- so the
        # DEFAULT_SCREENS fallback is showing on every boot, briefly, until
        # this fires with the device's real per-device config. AppManager
        # can't be reused to swap pages for an already-current app (it's a
        # no-op, see tmos_apps.py's set_current_app), so this replicates
        # what it does internally directly against window_manager.
        #
        # DashboardState.set() dispatches on every call, not only on
        # change (see state_store.py) -- a broker reconnect re-delivers
        # the same retained message, which would otherwise tear down and
        # rebuild every page (losing whichever screen the user was on)
        # for no reason. Skip the swap if this is the same config already
        # applied.
        if payload == self._applied_config:
            return
        self._applied_config = payload
        self._pages = self._build_pages(payload["screens"])
        self._window_manager.remove_all_pages()
        for page in self._pages:
            self._window_manager.add_page(page)
        self._window_manager.set_current_page(self._pages[0])

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
