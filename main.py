"""
Boot entry point. Wires config.py (tile/entity registry) + secrets.py
(WiFi/MQTT credentials) into DashboardApp and starts TmOS's run loop.

See scripts/preview_main.py for a no-broker, no-flash sanity check of the
grid/theme/tile layer alone (`mpremote run scripts/preview_main.py`).
"""

import config
import secrets

from tmos import OS
from tmos_ui import WindowManager
from tmos_apps import AppManager

from dashboard.app import DashboardApp
from dashboard.theme import CompressoTheme

os = OS(layers=1, full_res=True)
# layers=1: required for partial_update, which only works with 1 layer.
# full_res=True: required for a 480x480 display.get_bounds() (default is
# 240x240) -- every dashboard.grid constant is tuned for the 480px regime.
# Also raises dpi_scale_factor from 1 to 2, which is why dashboard/theme.py
# pins padding/systray_height to explicit final pixel values rather than
# relying on Theme's automatic dpi-scaling.

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
