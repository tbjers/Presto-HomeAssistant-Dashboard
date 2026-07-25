# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Minimal on-device smoke test — NOT the real main.py (which doesn't exist
yet). Run via `mpremote run` (does not persist to flash) after copying
tmos.py/tmos_ui.py/tmos_apps.py/tmos_themes.py/umqtt/dashboard/ to the
device. Proves two things the host-side pytest suite cannot:

1. TmOS itself boots to a blank page on real hardware with layers=1.
2. dashboard/'s no-__init__.py subpackage imports cleanly under MicroPython
   (CPython's implicit namespace packages let this pass on desktop
   regardless; umqtt ships the same way and is known to work on-device, but
   this hasn't been confirmed for OUR package yet).

Intentionally skips wifi/NTP/secrets.py — this only needs to prove import +
boot, not networking.
"""

from tmos import OS
from tmos_ui import WindowManager, StaticPage
from tmos_apps import App, AppManager

# Prove the vendored dashboard package imports cleanly on-device.
import dashboard.grid
import dashboard.palette
import dashboard.state_store
import dashboard.topics

print("dashboard.grid.tile_size(480) =", dashboard.grid.tile_size(480))
print("dashboard.palette.GRAY_950 =", dashboard.palette.GRAY_950)
print("dashboard.topics.state_topic('light', 'lamp') =", dashboard.topics.state_topic("light", "lamp"))

os = OS(layers=1)
wm = WindowManager(os)


class BlankPage(StaticPage):
    def _draw(self, display, region, theme):
        theme.clear_display(display, region)


class SmokeTestApp(App):
    name = "Smoke Test"

    def pages(self):
        return [BlankPage()]


apps = AppManager(wm)
apps.add_app(SmokeTestApp(), make_current=True)

print("Booted OK — should now show a blank themed screen.")
os.boot(run=True)
