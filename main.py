# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Boot entry point. Wires config.py (tile/entity registry) + secrets.py
(WiFi/MQTT credentials) into DashboardApp and starts TmOS's run loop.

See scripts/preview_main.py for a no-broker, no-flash sanity check of the
grid/theme/tile layer alone (`mpremote run scripts/preview_main.py`).
"""

import ntptime

import config
import secrets

from tmos import OS
from tmos_ui import WindowManager

from dashboard import settings as device_settings
from dashboard.app_manager import DashboardAppManager
from dashboard.splash import show as show_splash
from dashboard.theme import CompressoTheme
# dashboard.app is deliberately NOT imported up here -- it transitively
# imports dashboard.tiles -> dashboard.weather_icon -> dashboard.weather_icons,
# a sizeable table of baked MDI icon point data that MicroPython has to
# parse/compile on import. Since Python runs all top-level imports before any
# other top-level statement, importing it this early would make that parse
# cost part of the delay before show_splash(os) below ever paints anything --
# exactly the blank-screen wait splash.py exists to avoid. Imported instead
# just before first use, after the splash is already on screen.

ntptime.host = "time1.google.com"
# ntptime's own default, pool.ntp.org, timed out repeatedly on this network
# (tmos.py's __setup_network already docs "we seem to get timeouts
# frequently" for that host). Must be set before os.boot(use_ntp=True)
# below, which is what actually calls ntptime.settime().

os = OS(layers=1, full_res=True)
# layers=1: required for partial_update, which only works with 1 layer.
# full_res=True: required for a 480x480 display.get_bounds() (default is
# 240x240) -- every dashboard.grid constant is tuned for the 480px regime.
# Also raises dpi_scale_factor from 1 to 2, which is why dashboard/theme.py
# pins padding/systray_height to explicit final pixel values rather than
# relying on Theme's automatic dpi-scaling.

show_splash(os)
# Drawn straight to os.display before wifi/NTP connect (os.boot(wifi=True,
# ...) below blocks synchronously for that) and before WindowManager/App
# setup, so something appears immediately instead of a blank screen for
# however long the network takes. DashboardPage's first tick overdraws it
# once the run loop starts -- see dashboard/splash.py.

theme = CompressoTheme()
saved_settings = device_settings.load()
theme.font_choice = saved_settings["font_choice"]
# Must be set before WindowManager(...) below triggers theme.setup() --
# Theme.setup() (tmos_ui.py) is one-shot, so a font_choice set afterwards
# wouldn't take effect at boot (see dashboard/theme.py's module docstring;
# runtime switching after boot goes through apply_font_choice() instead,
# from dashboard/settings_page.py).
theme.corner_style = saved_settings["corner_style"]
theme.corner_radius = saved_settings["corner_radius"]

wm = WindowManager(os, theme=theme, systray_visible=True)
# systray_visible defaults to False -- AppManager below only registers the
# app-switcher button as systray *content*, it never flips this flag itself,
# so it has to be set explicitly here or the systray never renders at all.
apps = DashboardAppManager(wm)  # default systray_position -- app-switcher accessory on the leading edge
# DashboardAppManager (not vendored tmos_apps.AppManager directly) -- fixes
# a stale-screen bug in AppManager.open_switcher() where reselecting the
# already-current app from the hamburger menu clears the modal without
# ever repainting the page underneath. See dashboard/app_manager.py.

from dashboard.app import DashboardApp  # noqa: E402 -- see the top-of-file note
from dashboard.settings_page import SettingsApp  # noqa: E402 -- see the top-of-file note

dash_app = DashboardApp(config, secrets)
apps.add_app(dash_app, make_current=True)
# add_app() calls dash_app.setup(wm) immediately (constructs DashboardState
# + DashboardMQTT, not yet connected -- the mqtt.tick task drives the
# actual connection attempt, non-blocking, once the run loop starts).
# make_current=True pulls pages()/tasks() now, registering DashboardPage
# and the mqtt.tick task.

apps.add_app(SettingsApp(theme))
# Not make_current -- this just registers "Settings" as a second row in
# the existing hamburger/app-switcher list (tmos_apps.py's AppSwitcher),
# alongside "Dashboard". The dashboard stays the app shown at boot.

os.boot(wifi=True, use_ntp=True, run=True)
# wifi=True: presto.connect() reads secrets.py's WIFI_SSID/WIFI_PASSWORD.
# use_ntp=True: needed for DateTimeTile and for sane LWT/timestamp behavior.
# run=True: starts the asyncio run loop; blocks forever.
