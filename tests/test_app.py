"""
Tests for dashboard.app.DashboardApp.

Patches DashboardMQTT/DashboardPage at the dashboard.app import site so
this only exercises the wiring (what gets constructed with what), not
mqtt_client's/page's own behavior -- those have their own test modules.
"""

from types import SimpleNamespace
from unittest import mock

from tmos_apps import App

from dashboard.app import DashboardApp


def _config(**overrides):
    base = dict(
        DEVICE_ID="presto-office",
        DEFAULT_SCREENS=[{"title": "Dashboard", "tiles": [{"type": "datetime", "col": 0, "row": 0}]}],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _secrets(**overrides):
    base = dict(
        WIFI_SSID="ssid", WIFI_PASSWORD="pw",
        MQTT_HOST="broker.local", MQTT_PORT=1883, MQTT_USER="u", MQTT_PASSWORD="p",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestSetup:
    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_setup_constructs_mqtt_with_config_and_secrets(self, mqtt_cls, page_cls):
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=mock.Mock())

        _, kwargs = mqtt_cls.call_args
        assert kwargs["device_id"] == "presto-office"
        assert kwargs["host"] == "broker.local"
        assert kwargs["port"] == 1883
        assert kwargs["user"] == "u"
        assert kwargs["password"] == "p"

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_setup_constructs_a_page_per_default_screen(self, mqtt_cls, page_cls):
        config = _config()
        app = DashboardApp(config, _secrets())
        app.setup(window_manager=mock.Mock())

        page_cls.assert_called_once_with(
            "Dashboard", config.DEFAULT_SCREENS[0]["tiles"], app._state, mqtt_cls.return_value
        )

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_setup_defaults_missing_optional_secrets(self, mqtt_cls, page_cls):
        secrets = _secrets()
        del secrets.MQTT_USER
        del secrets.MQTT_PASSWORD
        app = DashboardApp(_config(), secrets)
        app.setup(window_manager=mock.Mock())

        _, kwargs = mqtt_cls.call_args
        assert kwargs["user"] is None
        assert kwargs["password"] is None


class TestPagesAndTasks:
    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_pages_returns_a_page_per_default_screen(self, mqtt_cls, page_cls):
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=mock.Mock())

        assert app.pages() == [page_cls.return_value]

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_pages_forces_needs_setup_on_every_call(self, mqtt_cls, page_cls):
        # Regression check: AppManager.set_current_app() (tmos_apps.py)
        # reuses these same page instances every time this app is made
        # current again, and WindowManager.remove_page()'s teardown() call
        # (when switching away) wipes their tile state without any vendored
        # code ever resetting page.needs_setup back to True -- so pages()
        # must force it itself, every call, or a page switched away from
        # and back to stays permanently blank. Confirmed on real hardware.
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=mock.Mock())
        page = page_cls.return_value
        page.needs_setup = False  # simulate a page that's already been torn down once

        app.pages()

        assert page.needs_setup is True

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_pages_returns_multiple_pages_for_multiple_default_screens(self, mqtt_cls, page_cls):
        config = _config(
            DEFAULT_SCREENS=[
                {"title": "Office", "tiles": []},
                {"title": "Bedroom", "tiles": []},
            ]
        )
        page_cls.side_effect = [mock.Mock(), mock.Mock()]
        app = DashboardApp(config, _secrets())
        app.setup(window_manager=mock.Mock())

        assert len(app.pages()) == 2

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_tasks_returns_mqtt_tick_as_an_app_task(self, mqtt_cls, page_cls):
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=mock.Mock())

        tasks = app.tasks()

        assert len(tasks) == 2
        assert isinstance(tasks[0], App.Task)
        assert tasks[0].fn == mqtt_cls.return_value.tick
        assert tasks[0].touch_forces_execution is False

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_tasks_returns_timezone_update_as_an_app_task(self, mqtt_cls, page_cls):
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=mock.Mock())

        tasks = app.tasks()

        assert isinstance(tasks[1], App.Task)
        assert tasks[1].fn == app._update_timezone
        assert tasks[1].touch_forces_execution is False


class TestConfigUpdate:
    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_remote_config_replaces_pages(self, mqtt_cls, page_cls):
        window_manager = mock.Mock()
        default_page = mock.Mock()
        remote_page = mock.Mock()
        page_cls.side_effect = [default_page, remote_page]
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=window_manager)

        app._on_config_update({"screens": [{"title": "Office", "tiles": [{"type": "datetime"}]}]})

        page_cls.assert_called_with("Office", [{"type": "datetime"}], app._state, mqtt_cls.return_value)
        assert app.pages() == [remote_page]

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_remote_config_swaps_window_manager_pages(self, mqtt_cls, page_cls):
        window_manager = mock.Mock()
        remote_page = mock.Mock()
        page_cls.side_effect = [mock.Mock(), remote_page]
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=window_manager)

        app._on_config_update({"screens": [{"title": "Office", "tiles": []}]})

        window_manager.remove_all_pages.assert_called_once()
        window_manager.add_page.assert_called_once_with(remote_page)
        window_manager.set_current_page.assert_called_once_with(remote_page)

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_remote_config_with_multiple_screens_adds_each_page(self, mqtt_cls, page_cls):
        window_manager = mock.Mock()
        office_page, bedroom_page = mock.Mock(), mock.Mock()
        page_cls.side_effect = [mock.Mock(), office_page, bedroom_page]
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=window_manager)

        app._on_config_update(
            {"screens": [{"title": "Office", "tiles": []}, {"title": "Bedroom", "tiles": []}]}
        )

        assert window_manager.add_page.call_args_list == [mock.call(office_page), mock.call(bedroom_page)]
        window_manager.set_current_page.assert_called_once_with(office_page)

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_state_store_update_on_device_config_key_triggers_page_swap(self, mqtt_cls, page_cls):
        window_manager = mock.Mock()
        remote_page = mock.Mock()
        page_cls.side_effect = [mock.Mock(), remote_page]
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=window_manager)

        app._state.set("device/config", {"screens": [{"title": "Office", "tiles": []}]})

        assert app.pages() == [remote_page]

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_repeated_identical_config_does_not_rebuild_pages(self, mqtt_cls, page_cls):
        # A broker reconnect re-delivers the same retained message --
        # DashboardState.set() dispatches on every call regardless of
        # whether the value changed, so this must be a no-op the second
        # time or the user's current screen would reset for no reason.
        window_manager = mock.Mock()
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=window_manager)
        payload = {"screens": [{"title": "Office", "tiles": []}]}

        app._on_config_update(payload)
        pages_after_first = app.pages()
        app._on_config_update(dict(payload))

        assert app.pages() == pages_after_first
        assert window_manager.remove_all_pages.call_count == 1


class TestUpdateTimezone:
    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    @mock.patch("dashboard.app.eastern_utc_offset", return_value=-4)
    def test_update_timezone_sets_os_utc_offset(self, offset_fn, mqtt_cls, page_cls):
        window_manager = mock.Mock()
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=window_manager)

        app._update_timezone()

        assert window_manager.os.utc_offset == -4
