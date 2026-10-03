# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Soak test for camera screens: boots the real main.py (real broker, real
retained config, real DashboardApp) and, once a CameraPage appears in the
config, makes it the current page and logs a status line every
REPORT_EVERY_S to serial:

    t=  12m mem_free=7012345 (min 6998000) fps=2.9 shown=2088 parsed=2090
        stream=streaming err=None backlight=on

Run via `mpremote run scripts/camera_soak_test.py` (blocks; Ctrl-C or kill
mpremote to stop, then `mpremote reset`). Set config.WATCHDOG_ENABLED =
False on the device first -- see CLAUDE.md: a WDT left armed by the
previously running main.py would fire during os.boot()'s blocking connect
before main.py's own feeder starts.

What to look for: mem_free flat (no leak across thousands of frames),
fps steady at the camera's rate, parsed - shown small (skips), stream
staying "streaming", and backlight staying "on" past TmOS's 30s dim /
600s sleep timeouts.

Works by wrapping OS.boot (to register the extra tasks just before the run
loop starts) and WindowManager.__init__ (to get at the window manager),
then importing main -- main.py itself is unmodified.
"""

import gc
import time

import tmos
import tmos_ui

from dashboard.camera_page import CameraPage

REPORT_EVERY_S = 60

_wm = []
_state = {"focused": None, "min_free": None, "start": None}

_orig_wm_init = tmos_ui.WindowManager.__init__


def _wm_init(self, *args, **kwargs):
    _orig_wm_init(self, *args, **kwargs)
    _wm.append(self)


tmos_ui.WindowManager.__init__ = _wm_init


def _camera_page():
    for page in _wm[0].pages():
        if isinstance(page, CameraPage):
            return page
    return None


def focus_camera():
    # Switch to the camera page once per page instance (a config re-swap
    # builds a new one), then leave navigation alone.
    if not _wm:
        return
    page = _camera_page()
    if page is not None and page is not _state["focused"]:
        _wm[0].set_current_page(page)
        _state["focused"] = page
        print("soak: switched to camera page", page.title)


def report():
    if _state["start"] is None:
        _state["start"] = time.ticks_ms()
    free = gc.mem_free()
    if _state["min_free"] is None or free < _state["min_free"]:
        _state["min_free"] = free
    page = _camera_page() if _wm else None
    stream = page._stream if page is not None else None
    fps = page.fps() if page is not None else None
    print(
        "soak: t={:4d}m mem_free={} (min {}) fps={} shown={} parsed={} stream={} err={} backlight={}".format(
            time.ticks_diff(time.ticks_ms(), _state["start"]) // 60000,
            free,
            _state["min_free"],
            "{:.1f}".format(fps) if fps else "-",
            stream.frames if stream else "-",
            stream.parts if stream else "-",
            stream.state if stream else "-",
            stream.last_error if stream else "-",
            _os[0].backlight_manager.display_phase if _os else "-",
        )
    )


_os = []
_orig_boot = tmos.OS.boot


def _boot(self, *args, **kwargs):
    _os.append(self)
    self.add_task(focus_camera, execution_frequency=1, touch_forces_execution=False)
    self.add_task(report, execution_frequency=1 / REPORT_EVERY_S, touch_forces_execution=False)
    return _orig_boot(self, *args, **kwargs)


tmos.OS.boot = _boot

import main  # noqa: E402,F401 -- runs the real boot + run loop; blocks forever
