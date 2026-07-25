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


def _config():
    return SimpleNamespace(DEVICE_ID="presto-office", TILES=[{"type": "datetime", "col": 0, "row": 0}])


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
    def test_setup_constructs_page_with_tiles_state_and_mqtt(self, mqtt_cls, page_cls):
        config = _config()
        app = DashboardApp(config, _secrets())
        app.setup(window_manager=mock.Mock())

        page_cls.assert_called_once_with(config.TILES, app._state, mqtt_cls.return_value)

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
    def test_pages_returns_the_constructed_page(self, mqtt_cls, page_cls):
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=mock.Mock())

        assert app.pages() == [page_cls.return_value]

    @mock.patch("dashboard.app.DashboardPage")
    @mock.patch("dashboard.app.DashboardMQTT")
    def test_tasks_returns_mqtt_tick_as_an_app_task(self, mqtt_cls, page_cls):
        app = DashboardApp(_config(), _secrets())
        app.setup(window_manager=mock.Mock())

        tasks = app.tasks()

        assert len(tasks) == 1
        assert isinstance(tasks[0], App.Task)
        assert tasks[0].fn == mqtt_cls.return_value.tick
        assert tasks[0].touch_forces_execution is False
