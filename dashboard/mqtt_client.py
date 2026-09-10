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

Two idle-hang fixes live here (see the project plan / the "idle hang"
investigation):

  * _BoundedMQTTClient below overrides wait_msg() so a stalled/half-open
    connection can't block the single cooperative run loop forever.
    Vendored umqtt.simple.wait_msg() does `self.sock.setblocking(True)`
    (== settimeout(None)) after reading the first byte, leaving every
    follow-on read (topic, payload, SUBACK) unbounded. One dead socket
    then freezes touch + display until a hard reset.

  * DashboardMQTT sends a PINGREQ every PING_INTERVAL_MS. umqtt.simple
    never pings on its own, and this app publishes nothing while idle, so
    without this the broker drops the session every ~1.5x keepalive and
    the device reconnects hundreds of times a day -- each reconnect a
    fresh chance to trip the bug above.
"""

import struct
import time

from umqtt.simple import MQTTClient

from dashboard import topics

MIN_BACKOFF_MS = 2000
MAX_BACKOFF_MS = 60000
CONNECT_TIMEOUT_S = 5
KEEPALIVE_S = 60
# keepalive / 2: comfortably inside the broker's ~1.5x keepalive grace
# window even if one ping's tick is skipped under load.
PING_INTERVAL_MS = 30000
# Bound every post-header socket read. Long enough that a legitimately
# fragmented PUBLISH on a LAN (sub-millisecond RTT) always completes,
# short enough that a genuinely stalled read frees the run loop well
# before the watchdog (dashboard/watchdog.py, ~8s) would fire.
SOCKET_TIMEOUT_S = 4

# Bounded RAM buffer for error reports raised while disconnected (notably
# the boot-reason report, generated before Wi-Fi/MQTT are up). Oldest is
# dropped on overflow; `seq` in each payload lets Node-RED see the gap.
MAX_PENDING_ERRORS = 8

# A read on a broken/stalled connection surfaces in assorted ways:
#   OSError        -- socket error, or a timeout that raises (CPython)
#   TypeError      -- `self.sock.read(1)[0]` when a bounded read returns
#                     None on timeout (some MicroPython stream ports)
#   IndexError     -- a short/empty read where the body expects N bytes
#   AssertionError -- umqtt.simple's inline `assert` on a malformed packet
# All mean "this connection is unusable"; the response to every one is to
# drop it and reconnect rather than let it kill the run loop.
DISCONNECT_ERRORS = (OSError, TypeError, IndexError, AssertionError)


class _BoundedMQTTClient(MQTTClient):
    """
    MQTTClient with a bounded wait_msg().

    umqtt/simple.py is vendored (VENDORING.md) and must not be hand-edited,
    so this is a subclass -- the same approach dashboard/app_manager.py's
    DashboardAppManager takes to a vendored AppManager bug.

    wait_msg() below is umqtt.simple.MQTTClient.wait_msg reproduced
    verbatim from the pinned vendored revision
    (VENDORING.md's umqtt.simple commit, umqtt/simple.py:197-228) with a
    SINGLE change: the mid-method `self.sock.setblocking(True)` --
    equivalent to settimeout(None), i.e. block forever -- becomes
    `self.sock.settimeout(SOCKET_TIMEOUT_S)`, so the follow-on reads raise
    instead of hanging. Re-check this against upstream when re-vendoring
    umqtt.simple.

    check_msg() is NOT overridden: the vendored version does
    `self.sock.setblocking(False)` and then calls wait_msg(), so the
    initial one-byte probe read stays non-blocking (returns None when no
    message is pending) and only the rest of the packet becomes
    timeout-bounded -- exactly what's wanted.
    """

    socket_timeout = SOCKET_TIMEOUT_S

    def wait_msg(self):
        res = self.sock.read(1)
        self.sock.settimeout(self.socket_timeout)  # was: self.sock.setblocking(True)
        if res is None:
            return None
        if res == b"":
            raise OSError(-1)
        if res == b"\xd0":  # PINGRESP
            sz = self.sock.read(1)[0]
            assert sz == 0
            return None
        op = res[0]
        if op & 0xF0 != 0x30:
            return op
        sz = self._recv_len()
        topic_len = self.sock.read(2)
        topic_len = (topic_len[0] << 8) | topic_len[1]
        topic = self.sock.read(topic_len)
        sz -= topic_len + 2
        if op & 6:
            pid = self.sock.read(2)
            pid = pid[0] << 8 | pid[1]
            sz -= 2
        msg = self.sock.read(sz)
        self.cb(topic, msg)
        if op & 6 == 2:
            pkt = bytearray(b"\x40\x02\0\0")
            struct.pack_into("!H", pkt, 2, pid)
            self.sock.write(pkt)
        elif op & 6 == 4:
            assert 0
        return op


class DashboardMQTT:
    def __init__(
        self,
        state,
        device_id,
        host,
        port=1883,
        user=None,
        password=None,
        keepalive=KEEPALIVE_S,
        boot_id="unknown",
    ):
        self._state = state
        self._device_id = device_id
        self._boot_id = boot_id
        self._error_topic = topics.device_error_topic(device_id)
        self._client = _BoundedMQTTClient(
            device_id, host, port=port, user=user, password=password, keepalive=keepalive
        )
        self._client.set_callback(self._on_message)
        self._client.set_last_will(
            topics.device_status_topic(device_id), "offline", retain=True, qos=0
        )
        self.connected = False
        self._next_attempt_at = 0
        self._next_ping_at = 0
        self._backoff_ms = MIN_BACKOFF_MS
        self._pending_errors = []
        self._error_seq = 0
        self._reporting = False

    def tick(self):
        """Registered as an App.Task. Non-blocking (bar SOCKET_TIMEOUT_S in
        the pathological stalled-read case): either attempts a connect (at
        most once per backoff window) or sends a due ping and polls for one
        pending message, and never sleeps."""
        if not self.connected:
            if time.ticks_diff(time.ticks_ms(), self._next_attempt_at) >= 0:
                self._connect()
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self._next_ping_at) >= 0:
            try:
                self._client.ping()
            except DISCONNECT_ERRORS:
                self._handle_disconnect()
                return
            self._next_ping_at = time.ticks_add(now, PING_INTERVAL_MS)
        try:
            self._client.check_msg()
        except DISCONNECT_ERRORS:
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
        except DISCONNECT_ERRORS:
            self._handle_disconnect()
            return False

    def report_error(self, level, context, message):
        """Publish a diagnostic error to presto/device/<id>/error, retained
        so it survives broker restarts and a freshly-connecting Node-RED.
        Queued (bounded) if not currently connected; the firmware never
        publishes an empty payload here, so the topic is only ever cleared
        from Node-RED. Never raises."""
        if self._reporting:
            # Re-entrancy guard: report_error -> publish -> OSError ->
            # _handle_disconnect is fine, but a future post_message() from
            # a disconnect path could loop back in here, and wait_msg()'s
            # self.cb (-> _on_message) runs mid-packet. Queue and bail.
            self._queue_error(level, context, message)
            return
        self._reporting = True
        try:
            payload = self._build_error(level, context, message)
            if self.connected:
                try:
                    self._client.publish(self._error_topic, payload, retain=True, qos=0)
                    return
                except DISCONNECT_ERRORS:
                    self._handle_disconnect()
            self._pending_errors.append(payload)
            self._trim_pending()
        except Exception:  # noqa: BLE001 -- diagnostics must never crash a caller
            pass
        finally:
            self._reporting = False

    def _queue_error(self, level, context, message):
        try:
            self._pending_errors.append(self._build_error(level, context, message))
            self._trim_pending()
        except Exception:  # noqa: BLE001
            pass

    def _build_error(self, level, context, message):
        self._error_seq += 1
        return topics.format_device_error_payload(
            self._boot_id, self._error_seq, level, context, message
        )

    def _trim_pending(self):
        while len(self._pending_errors) > MAX_PENDING_ERRORS:
            self._pending_errors.pop(0)

    def _flush_pending_errors(self):
        # Called inside _connect()'s try: an OSError here propagates to its
        # `except` and schedules a retry, same as a failed subscribe. Only
        # clears the queue once every payload is away.
        while self._pending_errors:
            self._client.publish(self._error_topic, self._pending_errors[0], retain=True, qos=0)
            self._pending_errors.pop(0)

    def _connect(self):
        try:
            self._client.connect(timeout=CONNECT_TIMEOUT_S)
            self._client.publish(
                topics.device_status_topic(self._device_id), "online", retain=True, qos=0
            )
            self._client.subscribe(topics.state_wildcard(), qos=0)
            self._client.subscribe(topics.BRIDGE_STATUS_TOPIC, qos=0)
            self._client.subscribe(topics.device_config_topic(self._device_id), qos=0)
            self._flush_pending_errors()
        except DISCONNECT_ERRORS:
            self._schedule_retry()
            return
        self.connected = True
        self._backoff_ms = MIN_BACKOFF_MS
        self._next_ping_at = time.ticks_add(time.ticks_ms(), PING_INTERVAL_MS)

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
