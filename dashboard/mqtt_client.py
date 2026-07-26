# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
DashboardMQTT -- owns umqtt.simple.MQTTClient's connection lifecycle
(connect, reconnect/backoff, LWT, wildcard subscribe) so app.py/page.py
never touch the client directly. Routing an incoming message into
DashboardState is the only "business logic" this module does, via
dashboard.topics' parse functions.

QoS 0 throughout: umqtt.simple.publish(qos=1) blocks in a wait_msg() loop
until a PUBACK arrives -- the same freeze-the-cooperative-run-loop hazard
this project already rejected umqtt.robust's reconnect() for (see
VENDORING.md). QoS 0 is fine given retained state + a LAN-only broker.

Reconnect is driven from tick(), called periodically as an App.Task,
instead of a blocking retry loop: connect() itself still blocks briefly
(bounded by CONNECT_TIMEOUT_S via the socket timeout), but the backoff
*between* attempts happens across separate tick() calls, not inside a
sleep loop, so TmOS's asyncio run loop keeps servicing touch/display in
between attempts.
"""

import time

from umqtt.simple import MQTTClient

from dashboard import topics

MIN_BACKOFF_MS = 2000
MAX_BACKOFF_MS = 60000
CONNECT_TIMEOUT_S = 5


class DashboardMQTT:
    def __init__(self, state, device_id, host, port=1883, user=None, password=None, keepalive=60):
        self._state = state
        self._device_id = device_id
        self._client = MQTTClient(
            device_id, host, port=port, user=user, password=password, keepalive=keepalive
        )
        self._client.set_callback(self._on_message)
        self._client.set_last_will(
            topics.device_status_topic(device_id), "offline", retain=True, qos=0
        )
        self.connected = False
        self._next_attempt_at = 0
        self._backoff_ms = MIN_BACKOFF_MS

    def tick(self):
        """Registered as an App.Task. Non-blocking: either attempts a
        connect (at most once per backoff window) or polls for one pending
        message, never both, and never sleeps."""
        if not self.connected:
            if time.ticks_diff(time.ticks_ms(), self._next_attempt_at) >= 0:
                self._connect()
            return
        try:
            self._client.check_msg()
        except OSError:
            self._handle_disconnect()

    def publish(self, topic, payload):
        """Best-effort: drops the message if not currently connected rather
        than queuing it -- retained state means the next state message (or
        reconnect + fresh state) is the source of truth, not this publish."""
        if not self.connected:
            return False
        try:
            self._client.publish(topic, payload, retain=False, qos=0)
            return True
        except OSError:
            self._handle_disconnect()
            return False

    def _connect(self):
        try:
            self._client.connect(timeout=CONNECT_TIMEOUT_S)
            self._client.publish(
                topics.device_status_topic(self._device_id), "online", retain=True, qos=0
            )
            self._client.subscribe(topics.state_wildcard(), qos=0)
            self._client.subscribe(topics.BRIDGE_STATUS_TOPIC, qos=0)
            self._client.subscribe(topics.device_config_topic(self._device_id), qos=0)
        except OSError:
            self._schedule_retry()
            return
        self.connected = True
        self._backoff_ms = MIN_BACKOFF_MS

    def _handle_disconnect(self):
        self.connected = False
        self._schedule_retry()

    def _schedule_retry(self):
        self._next_attempt_at = time.ticks_add(time.ticks_ms(), self._backoff_ms)
        self._backoff_ms = min(self._backoff_ms * 2, MAX_BACKOFF_MS)

    def _on_message(self, topic, payload):
        if isinstance(topic, (bytes, bytearray)):
            topic = topic.decode()

        if topic == topics.BRIDGE_STATUS_TOPIC:
            online = topics.parse_availability_payload(payload)
            if online is not None:
                self._state.set("bridge/status", online)
            return

        if topic == topics.device_config_topic(self._device_id):
            config = topics.parse_config_payload(payload)
            if config is not None:
                self._state.set("device/config", config)
            return

        parsed = topics.parse_topic(topic)
        if not parsed:
            return
        domain, slug, kind = parsed
        if kind != topics.STATE_KIND:
            return
        value = topics.parse_state_payload(domain, payload)
        self._state.set("{}/{}".format(domain, slug), value)
