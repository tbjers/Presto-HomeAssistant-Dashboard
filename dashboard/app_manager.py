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

from tmos_apps import App, AppManager, AppManagerAccessory, AppSwitcher


class DashboardAppManagerAccessory(AppManagerAccessory):
    """
    AppManagerAccessory (tmos_apps.py) with its button flush against the
    systray's own edges, rather than the vendored 2px inset -- without
    hand-editing that file (see VENDORING.md).

    dashboard.theme.CompressoTheme.draw_app_switcher_button() now draws its
    own foreground_pen outline around the button (see that method's
    comment), and CompressoTheme.draw_systray() already draws a matching
    foreground_pen border around the whole systray strip. The accessory's
    region is already flush with the systray's own edges (Systray.
    __setup_accessories, tmos_ui.py, hands it the raw strip region with no
    padding of its own) -- AppManagerAccessory.setup()'s 2px inset was the
    only thing separating the two, leaving a visible background-colored
    gap between the button's border and the systray's. Zeroing it makes
    the two borders coincide as one continuous line instead.
    """

    def setup(self, region, window_manager):
        button = self.AppSwitcherButton(region)
        button.on_button_up = self.on_open_switcher
        self._controls = [button]


class DashboardAppManager(AppManager):
    def __init__(self, window_manager, **kwargs):
        super().__init__(window_manager, **kwargs)
        # AppManager keeps its own window_manager reference name-mangled
        # (__window_manager, private to the base class) -- stash our own
        # rather than reach into that.
        self._window_manager = window_manager

    def systray_accessory(self):
        # AppManager.systray_accessory() (tmos_apps.py) builds a plain
        # AppManagerAccessory -- swap in DashboardAppManagerAccessory
        # above instead, replicating the two lines of wiring it does
        # (there's no super() call to reuse partway through since the
        # class to instantiate differs).
        accessory = DashboardAppManagerAccessory()
        accessory.on_open_switcher = self.open_switcher
        return accessory

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
