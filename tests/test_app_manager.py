"""
Tests for dashboard.app_manager.DashboardAppManager.
"""

from unittest import mock

import pytest

from tmos import Region
from tmos_apps import App

from dashboard.app_manager import DashboardAppManager, DashboardAppManagerAccessory


class _FakeApp(App):
    def __init__(self, name):
        self.name = name
        self._page = mock.Mock()

    def pages(self):
        return [self._page]


def _window_manager():
    return mock.Mock()


def _open_and_get_switcher(manager, window_manager):
    manager.open_switcher()
    return window_manager.show_modal_page.call_args.args[0]


class TestOpenSwitcher:
    def test_raises_if_no_apps_registered(self):
        manager = DashboardAppManager(_window_manager())

        with pytest.raises(RuntimeError):
            manager.open_switcher()

    def test_shows_a_modal_switcher(self):
        wm = _window_manager()
        manager = DashboardAppManager(wm)
        manager.add_app(_FakeApp("Dashboard"), make_current=True)

        manager.open_switcher()

        wm.show_modal_page.assert_called_once()

    def test_selecting_a_different_app_switches_and_repaints(self):
        wm = _window_manager()
        manager = DashboardAppManager(wm)
        dash = _FakeApp("Dashboard")
        settings = _FakeApp("Settings")
        manager.add_app(dash, make_current=True)
        manager.add_app(settings)
        switcher = _open_and_get_switcher(manager, wm)
        underlying_page = mock.Mock()
        wm.current_page = underlying_page

        switcher.on_app_changed(settings)

        wm.clear_modal_page.assert_called_once()
        assert manager.current_app is settings
        underlying_page.will_show.assert_called_once()

    def test_selecting_the_already_current_app_still_forces_a_repaint(self):
        # Regression check: AppManager.set_current_app() (tmos_apps.py) is
        # a no-op when the target app is already current ("if app is
        # self.__current_app: return"), and neither
        # WindowManager.clear_modal_page() nor a no-op set_current_page()
        # ever call will_show() on the page underneath (tmos_ui.py) -- so
        # reselecting the app you're already on (the natural way to "just
        # close" the hamburger menu without switching) would otherwise
        # clear the modal over a page that never gets told to repaint. See
        # dashboard/app_manager.py's module docstring.
        wm = _window_manager()
        manager = DashboardAppManager(wm)
        dash = _FakeApp("Dashboard")
        manager.add_app(dash, make_current=True)
        switcher = _open_and_get_switcher(manager, wm)
        underlying_page = mock.Mock()
        wm.current_page = underlying_page

        switcher.on_app_changed(dash)  # re-selecting the same, already-current app

        wm.clear_modal_page.assert_called_once()
        underlying_page.will_show.assert_called_once()

    def test_no_current_page_does_not_raise(self):
        wm = _window_manager()
        manager = DashboardAppManager(wm)
        dash = _FakeApp("Dashboard")
        manager.add_app(dash, make_current=True)
        switcher = _open_and_get_switcher(manager, wm)
        wm.current_page = None

        switcher.on_app_changed(dash)  # should not raise


class TestSystrayAccessory:
    def test_uses_the_flush_dashboard_accessory(self):
        # Regression check: DashboardAppManager must register
        # DashboardAppManagerAccessory (dashboard/app_manager.py), not the
        # vendored AppManagerAccessory (tmos_apps.py) AppManager.__init__
        # would otherwise use -- see that class's docstring for why (a
        # visible gap between the hamburger button's own outline and the
        # systray's border).
        wm = _window_manager()

        DashboardAppManager(wm)

        accessory = wm.add_systray_accessory.call_args.args[0]
        assert isinstance(accessory, DashboardAppManagerAccessory)

    def test_button_region_is_flush_with_the_full_accessory_region(self):
        # AppManagerAccessory.setup() (tmos_apps.py) insets the button by
        # 2px; DashboardAppManagerAccessory must not, so its own outline
        # (dashboard.theme.CompressoTheme.draw_app_switcher_button) sits
        # flush against draw_systray()'s border instead of leaving a gap.
        accessory = DashboardAppManagerAccessory()
        region = Region(0, 450, 30, 30)

        accessory.setup(region, _window_manager())

        assert accessory._controls[0].region == region
