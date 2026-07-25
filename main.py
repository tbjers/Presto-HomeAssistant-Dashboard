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
from tmos_apps import AppManager

from dashboard.app import DashboardApp
from dashboard.splash import show as show_splash
from dashboard.theme import CompressoTheme

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

wm = WindowManager(os, theme=CompressoTheme())
apps = AppManager(wm)  # default systray_position -- systray stays visible

dash_app = DashboardApp(config, secrets)
apps.add_app(dash_app, make_current=True)
# add_app() calls dash_app.setup(wm) immediately (constructs DashboardState
# + DashboardMQTT, not yet connected -- the mqtt.tick task drives the
# actual connection attempt, non-blocking, once the run loop starts).
# make_current=True pulls pages()/tasks() now, registering DashboardPage
# and the mqtt.tick task.

os.boot(wifi=True, use_ntp=True, run=True)
# wifi=True: presto.connect() reads secrets.py's WIFI_SSID/WIFI_PASSWORD.
# use_ntp=True: needed for DateTimeTile and for sane LWT/timestamp behavior.
# run=True: starts the asyncio run loop; blocks forever.
