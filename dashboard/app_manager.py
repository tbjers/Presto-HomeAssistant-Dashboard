# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
DashboardAppManager(AppManager) -- fixes a stale-screen bug in the vendored
AppManager.open_switcher() (tmos_apps.py) without hand-editing that file
(see VENDORING.md).

Confirmed from source (tmos_ui.py):
- WindowManager.clear_modal_page() clears the modal but never calls
  will_show() on the page underneath.
- WindowManager.__upadate_pages() -- the only other place that calls
  will_show() -- compares current_page to last_page and skips the
  will_hide()/will_show() pair entirely when they're equal.
- AppManager.set_current_app() (tmos_apps.py) no-ops immediately
  ("if app is self.__current_app: return") whenever the app passed to it
  is already the active one -- leaving current_page unchanged.

So: open the hamburger/app-switcher, tap the app you're already on (the
natural way to "just close it" without switching), and the modal clears
over a page that never gets a repaint request -- exactly the same class of
bug DetailModalPage._close_modal (dashboard/modal.py) already works around
for tile-detail modals, just in AppManager's own vendored modal-closing
path instead. Switching to a genuinely *different* app isn't affected --
WindowManager's own next-tick page-transition detection already fires
will_show() for it (current_page != last_page there) -- so the extra call
here is at most a harmless redundant will_show() in that case.
"""

from tmos_apps import App, AppManager, AppSwitcher


class DashboardAppManager(AppManager):
    def __init__(self, window_manager, **kwargs):
        super().__init__(window_manager, **kwargs)
        # AppManager keeps its own window_manager reference name-mangled
        # (__window_manager, private to the base class) -- stash our own
        # rather than reach into that.
        self._window_manager = window_manager

    def open_switcher(self):
        if not self.apps():
            raise RuntimeError("No apps registered")

        def select_app(app: App):
            self._window_manager.clear_modal_page()
            self.set_current_app(app)
            underlying = self._window_manager.current_page
            if underlying is not None:
                underlying.will_show()

        switcher = AppSwitcher(self.apps())
        switcher.on_app_changed = select_app
        self._window_manager.show_modal_page(switcher)
