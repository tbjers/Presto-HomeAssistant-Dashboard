"""
Tests for dashboard.app_manager.DashboardAppManager.
"""

from unittest import mock

import pytest

from tmos_apps import App

from dashboard.app_manager import DashboardAppManager


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
