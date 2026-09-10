# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
On-device smoke test for dashboard.splash.show() -- NOT part of the app. Run
via `mpremote run` (does not persist to flash). Draws the splash exactly the
way main.py does right after OS() construction, so the new logo/label can be
visually checked on real hardware without waiting through a full wifi/NTP
boot.
"""

import time

from tmos import OS
from dashboard import splash

os = OS(layers=1, full_res=True)
splash.show(os, status="Starting")
print("Splash drawn -- check screen for centered logo + 'BOOTING INTERFACE' label.")

for status in ("Loading modules", "Preparing dashboard", "Connecting to WiFI", "Setting time"):
    time.sleep(1)
    splash.set_status(os, status)
    print("  status ->", status)
print("Status line should have cycled through each label near the bottom edge.")
