"""
Tests for dashboard.mqtt_client.

Patches dashboard.mqtt_client._BoundedMQTTClient (not umqtt.simple) for the
DashboardMQTT lifecycle tests, so its own logic -- backoff, keepalive
pings, message routing, the error-report queue -- is what's exercised, not
umqtt's wire protocol.

TestBoundedWaitMsg drives the real _BoundedMQTTClient.wait_msg against a
scripted fake socket -- that override is the idle-hang fix and can't be
tested through the mock.
"""

import time
from unittest import mock

import pytest

from dashboard import topics
from dashboard.mqtt_client import (
    MAX_BACKOFF_MS,
    MAX_PENDING_ERRORS,
    MIN_BACKOFF_MS,
    PING_INTERVAL_MS,
    SOCKET_TIMEOUT_S,
    DashboardMQTT,
    _BoundedMQTTClient,
)
from dashboard.state_store import DashboardState


def _mqtt(mqtt_client_cls, **kwargs):
    return DashboardMQTT(DashboardState(), "presto-test", "broker.local", **kwargs)


class TestConstruction:
    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
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

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_boot_id_defaults_to_unknown(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        assert dash._boot_id == "unknown"

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_boot_id_is_stored_when_supplied(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls, boot_id="cafef00d")
        assert dash._boot_id == "cafef00d"


class TestTickConnecting:
    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_tick_attempts_connect_when_due(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)

        dash.tick()

        mqtt_client_cls.return_value.connect.assert_called_once()

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_successful_connect_marks_connected_and_resets_backoff(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash._backoff_ms = 32000

        dash.tick()

        assert dash.connected is True
        assert dash._backoff_ms == MIN_BACKOFF_MS

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_successful_connect_publishes_online_and_subscribes(self, mqtt_client_cls):
        client = mqtt_client_cls.return_value
        dash = _mqtt(mqtt_client_cls)

        dash.tick()

        client.publish.assert_any_call(
            topics.device_status_topic("presto-test"), "online", retain=True, qos=0
        )
        client.subscribe.assert_any_call(topics.state_wildcard(), qos=0)
        client.subscribe.assert_any_call(topics.BRIDGE_STATUS_TOPIC, qos=0)
        client.subscribe.assert_any_call(topics.device_config_topic("presto-test"), qos=0)

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_successful_connect_schedules_first_ping(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)

        before = time.ticks_ms()
        dash.tick()

        assert time.ticks_diff(dash._next_ping_at, before) >= PING_INTERVAL_MS - 50

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_failed_connect_schedules_retry_and_stays_disconnected(self, mqtt_client_cls):
        mqtt_client_cls.return_value.connect.side_effect = OSError()
        dash = _mqtt(mqtt_client_cls)

        dash.tick()

        assert dash.connected is False
        assert dash._backoff_ms == MIN_BACKOFF_MS * 2

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_backoff_doubles_and_caps_at_max_on_repeated_failures(self, mqtt_client_cls):
        mqtt_client_cls.return_value.connect.side_effect = OSError()
        dash = _mqtt(mqtt_client_cls)

        for _ in range(20):
            dash._next_attempt_at = time.ticks_ms()
            dash.tick()

        assert dash._backoff_ms == MAX_BACKOFF_MS

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_tick_does_not_attempt_connect_before_backoff_elapses(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash._next_attempt_at = time.ticks_add(time.ticks_ms(), MIN_BACKOFF_MS)

        dash.tick()

        mqtt_client_cls.return_value.connect.assert_not_called()


class TestTickConnected:
    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_tick_polls_check_msg_when_connected(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True
        dash._next_ping_at = time.ticks_add(time.ticks_ms(), PING_INTERVAL_MS)

        dash.tick()

        mqtt_client_cls.return_value.check_msg.assert_called_once()

    @pytest.mark.parametrize("exc", [OSError(), TypeError(), IndexError(), AssertionError()])
    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_check_msg_failure_marks_disconnected_and_schedules_retry(self, mqtt_client_cls, exc):
        # A stalled/half-open read surfaces as OSError, or -- on some
        # MicroPython stream ports where a timed-out read returns None --
        # as TypeError/IndexError from the parse, or AssertionError from
        # umqtt's inline asserts. All must be caught, not kill the run loop.
        mqtt_client_cls.return_value.check_msg.side_effect = exc
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True
        dash._next_ping_at = time.ticks_add(time.ticks_ms(), PING_INTERVAL_MS)

        dash.tick()

        assert dash.connected is False
        assert dash._backoff_ms == MIN_BACKOFF_MS * 2


class TestKeepalivePing:
    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_ping_sent_when_interval_elapsed(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True
        dash._next_ping_at = time.ticks_add(time.ticks_ms(), -1)

        dash.tick()

        mqtt_client_cls.return_value.ping.assert_called_once()
        assert time.ticks_diff(dash._next_ping_at, time.ticks_ms()) > 0

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_ping_not_sent_before_interval(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True
        dash._next_ping_at = time.ticks_add(time.ticks_ms(), PING_INTERVAL_MS)

        dash.tick()

        mqtt_client_cls.return_value.ping.assert_not_called()

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_ping_failure_marks_disconnected_and_skips_check_msg(self, mqtt_client_cls):
        client = mqtt_client_cls.return_value
        client.ping.side_effect = OSError()
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True
        dash._next_ping_at = time.ticks_add(time.ticks_ms(), -1)

        dash.tick()

        assert dash.connected is False
        client.check_msg.assert_not_called()


class TestPublish:
    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_publish_while_connected_forwards_qos0_no_retain(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True

        result = dash.publish("presto/light/lamp/set", b'{"state":"on"}')

        mqtt_client_cls.return_value.publish.assert_called_once_with(
            "presto/light/lamp/set", b'{"state":"on"}', retain=False, qos=0
        )
        assert result is True

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_publish_while_disconnected_is_a_no_op(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)

        result = dash.publish("presto/light/lamp/set", b"{}")

        mqtt_client_cls.return_value.publish.assert_not_called()
        assert result is False

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_publish_failure_marks_disconnected_and_returns_false(self, mqtt_client_cls):
        mqtt_client_cls.return_value.publish.side_effect = OSError()
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True

        result = dash.publish("presto/light/lamp/set", b"{}")

        assert result is False
        assert dash.connected is False


class TestReportError:
    def _sole_error(self, client):
        calls = [
            c
            for c in client.publish.call_args_list
            if c.args and c.args[0] == topics.device_error_topic("presto-test")
        ]
        assert len(calls) == 1
        topic, payload = calls[0].args
        assert calls[0].kwargs == {"retain": True, "qos": 0}
        return topics.parse_device_error_payload(payload)

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_reports_retained_to_error_topic_when_connected(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls, boot_id="abc123")
        dash.connected = True

        dash.report_error(topics.ERROR_LEVEL_FATAL, "mqtt", "socket exploded")

        parsed = self._sole_error(mqtt_client_cls.return_value)
        assert parsed == {
            "boot_id": "abc123",
            "seq": 1,
            "level": "fatal",
            "context": "mqtt",
            "message": "socket exploded",
        }

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_seq_increments_per_report(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True

        dash.report_error("warning", "a", "one")
        dash.report_error("warning", "b", "two")

        seqs = [
            topics.parse_device_error_payload(c.args[1])["seq"]
            for c in mqtt_client_cls.return_value.publish.call_args_list
            if c.args[0] == topics.device_error_topic("presto-test")
        ]
        assert seqs == [1, 2]

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_queues_while_disconnected_then_flushes_after_subscribe(self, mqtt_client_cls):
        client = mqtt_client_cls.return_value
        dash = _mqtt(mqtt_client_cls)

        dash.report_error("fatal", "boot", "recovered from unexpected reset (watchdog)")
        client.publish.assert_not_called()
        assert len(dash._pending_errors) == 1

        dash.tick()  # connects

        # error publish happens, and only after the subscribes
        publish_topics = [c.args[0] for c in client.publish.call_args_list]
        assert topics.device_error_topic("presto-test") in publish_topics
        assert client.subscribe.call_count == 3
        assert dash._pending_errors == []

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_pending_queue_is_bounded_dropping_oldest(self, mqtt_client_cls):
        dash = _mqtt(mqtt_client_cls)

        for i in range(MAX_PENDING_ERRORS + 3):
            dash.report_error("warning", "spam", "msg {}".format(i))

        assert len(dash._pending_errors) == MAX_PENDING_ERRORS
        first = topics.parse_device_error_payload(dash._pending_errors[0])
        assert first["message"] == "msg 3"  # 0,1,2 dropped

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_publish_failure_during_report_queues_and_disconnects(self, mqtt_client_cls):
        client = mqtt_client_cls.return_value
        client.publish.side_effect = OSError()
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True

        dash.report_error("fatal", "mqtt", "boom")

        assert dash.connected is False
        assert len(dash._pending_errors) == 1

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_reentrant_report_is_queued_not_published(self, mqtt_client_cls):
        client = mqtt_client_cls.return_value
        dash = _mqtt(mqtt_client_cls)
        dash.connected = True
        dash._reporting = True

        dash.report_error("fatal", "mqtt", "nested")

        client.publish.assert_not_called()
        assert len(dash._pending_errors) == 1


class TestOnMessage:
    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_state_message_updates_dashboard_state(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(b"presto/light/lamp/state", b'{"state": "on"}')

        assert state.get("light/lamp") == {"state": "on"}

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_set_topic_is_ignored(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(b"presto/light/lamp/set", b'{"state": "on"}')

        assert state.get("light/lamp") is None

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_bridge_status_topic_updates_bridge_status_key(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(topics.BRIDGE_STATUS_TOPIC.encode(), b"online")

        assert state.get("bridge/status") is True

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_config_topic_updates_device_config_key(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")
        raw = b'{"screens": [{"title": "Dashboard", "tiles": [{"type": "datetime"}]}]}'

        dash._on_message(topics.device_config_topic("presto-test").encode(), raw)

        assert state.get("device/config") == {
            "screens": [{"title": "Dashboard", "tiles": [{"type": "datetime"}]}]
        }

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_malformed_config_payload_does_not_update_state(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(topics.device_config_topic("presto-test").encode(), b"not json")

        assert state.get("device/config") is None

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_malformed_topic_is_ignored_without_raising(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(b"garbage", b"{}")  # must not raise

    @mock.patch("dashboard.mqtt_client._BoundedMQTTClient")
    def test_malformed_payload_stores_none_rather_than_raising(self, mqtt_client_cls):
        state = DashboardState()
        dash = DashboardMQTT(state, "presto-test", "broker.local")

        dash._on_message(b"presto/light/lamp/state", b"not json")

        assert state.get("light/lamp") is None


class _FakeSocket:
    """Scripted socket for _BoundedMQTTClient.wait_msg. Each `reads` entry
    is returned (bytes / None) or raised (exception) on successive read()
    calls."""

    def __init__(self, reads):
        self._reads = list(reads)
        self.timeout = "unset"
        self.writes = []
        self.mode_calls = []  # ordered ("setblocking"|"settimeout", arg)

    def read(self, n=None):
        assert self._reads, "wait_msg read past the end of the script"
        item = self._reads.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def write(self, *args):
        self.writes.append(args)

    def setblocking(self, flag):
        self.mode_calls.append(("setblocking", flag))

    def settimeout(self, value):
        self.timeout = value
        self.mode_calls.append(("settimeout", value))


def _bounded_client():
    client = _BoundedMQTTClient("id", "host")
    received = []
    client.set_callback(lambda topic, msg: received.append((topic, msg)))
    return client, received


class TestBoundedWaitMsg:
    def test_parses_publish_and_invokes_callback(self):
        client, received = _bounded_client()
        # PUBLISH qos0: op=0x30, remaining-len=7, topiclen=0x0003, "a/b", "{}"
        client.sock = _FakeSocket([b"\x30", b"\x07", b"\x00\x03", b"a/b", b"{}"])

        op = client.wait_msg()

        assert op == 0x30
        assert received == [(b"a/b", b"{}")]

    def test_bounds_the_socket_after_the_first_byte(self):
        client, _ = _bounded_client()
        sock = _FakeSocket([b"\x30", b"\x07", b"\x00\x03", b"a/b", b"{}"])
        client.sock = sock

        client.wait_msg()

        # The vendored body does `self.sock.setblocking(True)` right after
        # the first byte -- the override must replace that with a bounded
        # settimeout and must NOT also blocking-True the socket (a re-vendor
        # reintroducing the line would otherwise slip past a bare
        # `timeout == SOCKET_TIMEOUT_S` check).
        assert ("setblocking", True) not in sock.mode_calls
        assert sock.mode_calls == [("settimeout", SOCKET_TIMEOUT_S)]
        assert sock.timeout == SOCKET_TIMEOUT_S

    def test_stalled_followon_read_raises_instead_of_hanging(self):
        client, _ = _bounded_client()
        sock = _FakeSocket([b"\x30", OSError("stalled")])
        client.sock = sock

        with pytest.raises(OSError):
            client.wait_msg()
        assert sock.timeout == SOCKET_TIMEOUT_S

    def test_timeout_read_returning_none_surfaces_as_typeerror(self):
        # Documents the MicroPython-stream case the advisor flagged: a
        # timed-out read yields None, and _recv_len's `read(1)[0]` then
        # raises TypeError -- which tick() catches (see
        # TestTickConnected.test_check_msg_failure...).
        client, _ = _bounded_client()
        client.sock = _FakeSocket([b"\x30", None])

        with pytest.raises(TypeError):
            client.wait_msg()

    def test_empty_probe_read_returns_none(self):
        client, _ = _bounded_client()
        client.sock = _FakeSocket([None])

        assert client.wait_msg() is None

    def test_broken_connection_probe_raises_oserror(self):
        client, _ = _bounded_client()
        client.sock = _FakeSocket([b""])

        with pytest.raises(OSError):
            client.wait_msg()

    def test_pingresp_is_consumed_quietly(self):
        client, received = _bounded_client()
        client.sock = _FakeSocket([b"\xd0", b"\x00"])

        assert client.wait_msg() is None
        assert received == []
