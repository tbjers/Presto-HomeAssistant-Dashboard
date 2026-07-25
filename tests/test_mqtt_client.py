"""
Tests for dashboard.mqtt_client.DashboardMQTT.

Patches dashboard.mqtt_client.MQTTClient itself (not umqtt.simple -- that
module is plain-stdlib and imports fine under CPython, but we never want a
real socket in these tests), so DashboardMQTT's own connection-lifecycle
logic (backoff scheduling, LWT/subscribe wiring, message routing) is what's
under test, not umqtt.simple's wire protocol.
"""

import time
from unittest import mock

from dashboard import topics
from dashboard.mqtt_client import MAX_BACKOFF_MS, MIN_BACKOFF_MS, DashboardMQTT
from dashboard.state_store import DashboardState


def _mqtt(mqtt_client_cls, **kwargs):
    return DashboardMQTT(DashboardState(), "presto-test", "broker.local", **kwargs)


class TestConstruction:
    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_configures_callback_and_last_will(self, mqtt_client_cls):
        client = mqtt_client_cls.return_value
        dash = _mqtt(mqtt_client_cls, user="u", password="p")

        mqtt_client_cls.assert_called_once_with(
            "presto-test", "broker.local", port=1883, user="u", password="p", keepalive=60
        )
        client.set_callback.assert_called_once_with(dash._on_message)
        client.set_last_will.assert_called_once_with(
            topics.device_status_topic("presto-test"), "offline", retain=True, qos=0
        )
        assert dash.connected is False


class TestTickConnecting:
    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_tick_attempts_connect_when_due(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)

        dash.tick()

        mqtt_client_cls.return_value.connect.assert_called_once()

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_successful_connect_marks_connected_and_resets_backoff(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash._backoff_ms = 32000

        dash.tick()

        assert dash.connected is True
        assert dash._backoff_ms == MIN_BACKOFF_MS

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_successful_connect_publishes_online_and_subscribes(self, mqtt_client_cls):
        client = mqtt_client_cls.return_value
        dash = _mqtt(mqtt_client_cls)

        dash.tick()

        client.publish.assert_called_once_with(
            topics.device_status_topic("presto-test"), "online", retain=True, qos=0
        )
        client.subscribe.assert_any_call(topics.state_wildcard(), qos=0)
        client.subscribe.assert_any_call(topics.BRIDGE_STATUS_TOPIC, qos=0)

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_failed_connect_schedules_retry_and_stays_disconnected(self, mqtt_client_cls):
        mqtt_client_cls.return_value.connect.side_effect = OSError()
        dash = _mqtt(mqtt_client_cls)

        dash.tick()

        assert dash.connected is False
        assert dash._backoff_ms == MIN_BACKOFF_MS * 2

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_backoff_doubles_and_caps_at_max_on_repeated_failures(self, mqtt_client_cls):
        mqtt_client_cls.return_value.connect.side_effect = OSError()
        dash = _mqtt(mqtt_client_cls)

        for _ in range(20):
            dash._next_attempt_at = time.ticks_ms()  # force each attempt to be due
            dash.tick()

        assert dash._backoff_ms == MAX_BACKOFF_MS

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_tick_does_not_attempt_connect_before_backoff_elapses(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash._next_attempt_at = time.ticks_add(time.ticks_ms(), MIN_BACKOFF_MS)

        dash.tick()

        mqtt_client_cls.return_value.connect.assert_not_called()


class TestTickConnected:
    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_tick_polls_check_msg_when_connected(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True

        dash.tick()

        mqtt_client_cls.return_value.check_msg.assert_called_once()

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_check_msg_oserror_marks_disconnected_and_schedules_retry(self, mqtt_client_cls):
        mqtt_client_cls.return_value.check_msg.side_effect = OSError()
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True

        dash.tick()

        assert dash.connected is False
        assert dash._backoff_ms == MIN_BACKOFF_MS * 2


class TestPublish:
    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_publish_while_connected_forwards_qos0_no_retain(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True

        result = dash.publish("presto/light/lamp/set", b'{"state":"on"}')

        mqtt_client_cls.return_value.publish.assert_called_once_with(
            "presto/light/lamp/set", b'{"state":"on"}', retain=False, qos=0
        )
        assert result is True

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_publish_while_disconnected_is_a_no_op(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)

        result = dash.publish("presto/light/lamp/set", b"{}")

        mqtt_client_cls.return_value.publish.assert_not_called()
        assert result is False

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_publish_oserror_marks_disconnected_and_returns_false(self, mqtt_client_cls):
        mqtt_client_cls.return_value.publish.side_effect = OSError()
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True

        result = dash.publish("presto/light/lamp/set", b"{}")

        assert result is False
        assert dash.connected is False


class TestOnMessage:
    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_state_message_updates_dashboard_state(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(b"presto/light/lamp/state", b'{"state": "on"}')

        assert state.get("light/lamp") == {"state": "on"}

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_set_topic_is_ignored(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(b"presto/light/lamp/set", b'{"state": "on"}')

        assert state.get("light/lamp") is None

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_bridge_status_topic_updates_bridge_status_key(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(topics.BRIDGE_STATUS_TOPIC.encode(), b"online")

        assert state.get("bridge/status") is True

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_malformed_topic_is_ignored_without_raising(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(b"garbage", b"{}")  # must not raise

    @mock.patch("dashboard.mqtt_client.MQTTClient")
    def test_malformed_payload_stores_none_rather_than_raising(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(b"presto/light/lamp/state", b"not json")

        assert state.get("light/lamp") is None
