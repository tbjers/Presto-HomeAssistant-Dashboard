# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
On-device probe for the idle-hang / device-error work. Run via
`mpremote run scripts/device_error_smoke_test.py` -- does not touch
flash/main.py. Mirrors scripts/mqtt_smoke_test.py's isolation approach.

IMPORTANT: if the flashed main.py has config.WATCHDOG_ENABLED = True, its
machine.WDT survives mpremote's soft reset and this script inherits an
unfed ~8s watchdog -- it fires mid-run and shows up host-side as a serial
ClearCommError, not a device traceback. feed_wdt() below re-arms + feeds
defensively, but the clean way to bench-test is: set
config.WATCHDOG_ENABLED = False, `mpremote cp config.py :`, `mpremote
reset`, then run this. Restore True afterwards.

Checks host-side pytest cannot:

1. machine.reset_cause() -- CONFIRMED binary on RP2350 (always "watchdog"
   for a software reboot, "power" for cold boot / reset button), which is
   why diagnostics.py uses an uptime breadcrumb instead. Also exercises
   the breadcrumb read/reset round-trip.

2. How a bounded-timeout socket read fails on this port -- CONFIRMED it
   raises OSError(110) ETIMEDOUT.

3. The retained device-error topic round-trips: publish via
   DashboardMQTT.report_error, read it back through
   topics.parse_device_error_payload.

4. Keepalive: DashboardMQTT.tick() driven past the broker's ~90s drop
   window with no other traffic. The broker's own session view (one
   stable session, no 90s reconnect pairs) is the more reliable check.
"""

import time

from tmos import OS

import config
import secrets

from dashboard import diagnostics, topics
from dashboard.mqtt_client import SOCKET_TIMEOUT_S, DashboardMQTT
from dashboard.state_store import DashboardState

_wdt_feed_reported = False


def feed_wdt():
    """A flashed main.py arms machine.WDT (config.WATCHDOG_ENABLED); mpremote's
    soft reset does NOT clear it, so an unfed WDT fires ~8s into any script
    run after a main.py boot -- which shows up host-side as a serial
    ClearCommError, not a device traceback. Re-arm + feed defensively;
    harmless if none was running. Call before os.boot() and in every wait
    loop. (Cleaner: set config.WATCHDOG_ENABLED = False, redeploy, reset,
    then run bench scripts.)"""
    global _wdt_feed_reported
    try:
        from machine import WDT

        WDT(timeout=8388).feed()
        outcome = "armed/fed ok"
    except Exception as exc:  # noqa: BLE001
        outcome = "WDT() raised: {!r}".format(exc)
    if not _wdt_feed_reported:
        print("  [wdt] defensive feed:", outcome)
        _wdt_feed_reported = True


def probe_reset_cause():
    print("--- 1. reset cause + boot breadcrumb ---")
    try:
        import machine

        raw = machine.reset_cause()
    except Exception as exc:  # noqa: BLE001
        print("  machine.reset_cause() unavailable:", exc)
    else:
        print("  machine.reset_cause() =", raw)
    print("  diagnostics.reset_reason() =", diagnostics.reset_reason())
    print("  BOOT_ID =", diagnostics.BOOT_ID)
    try:
        with open("diag_state.json") as f:
            print("  on-flash diag_state.json =", f.read())
        print("  ({'long_run': true, ...} => the flashed main.py's last session likely hung)")
    except OSError:
        print("  on-flash diag_state.json = <none yet>")
    # non-destructive: exercise the read/reset round-trip on a scratch path
    diagnostics.init_boot_state("diag_smoke_test.json")
    print("  init_boot_state round-trip previous_run() =", diagnostics.previous_run())


def probe_timeout_read():
    print("--- 2. bounded-read failure mode ---")
    import socket

    s = socket.socket()
    try:
        s.connect(socket.getaddrinfo(secrets.MQTT_HOST, getattr(secrets, "MQTT_PORT", 1883))[0][-1])
        s.settimeout(1)
        print("  reading from an idle (connected, silent) socket with settimeout(1)...")
        try:
            result = s.read(1)
            print("  -> returned", repr(result))
        except OSError as exc:
            print("  -> raised OSError, errno/args =", exc.args)
        except Exception as exc:  # noqa: BLE001
            print("  -> raised", type(exc).__name__, exc.args)
    finally:
        s.close()


def main():
    feed_wdt()  # BEFORE os.boot() -- ntptime.timeout alone can exceed the WDT window
    print("connecting wifi...")
    os = OS(layers=1, full_res=True)
    os.boot(wifi=True, use_ntp=True, run=False)
    feed_wdt()
    print("wifi connected\n")

    probe_reset_cause()
    feed_wdt()
    print()
    probe_timeout_read()
    feed_wdt()
    print()

    print("--- 3. retained error topic round-trip ---")
    state = DashboardState()
    mqtt = DashboardMQTT(
        state,
        device_id=config.DEVICE_ID,
        host=secrets.MQTT_HOST,
        port=getattr(secrets, "MQTT_PORT", 1883),
        user=getattr(secrets, "MQTT_USER", None),
        password=getattr(secrets, "MQTT_PASSWORD", None),
        boot_id=diagnostics.BOOT_ID,
    )
    # queued now, flushed on connect
    mqtt.report_error(topics.ERROR_LEVEL_WARNING, "smoke_test", "hello from device_error_smoke_test")

    error_topic = topics.device_error_topic(config.DEVICE_ID)
    seen = []
    mqtt._client.set_callback(lambda t, m: seen.append((t, m)))

    print("  connecting mqtt (SOCKET_TIMEOUT_S = {}s)...".format(SOCKET_TIMEOUT_S))
    for _ in range(50):
        feed_wdt()
        mqtt.tick()
        if mqtt.connected:
            break
        time.sleep_ms(200)
    print("  connected =", mqtt.connected)

    mqtt._client.subscribe(error_topic.encode())
    deadline = time.ticks_add(time.ticks_ms(), 3000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        feed_wdt()
        mqtt.tick()
        time.sleep_ms(100)
    for topic, msg in seen:
        if topic.decode() == error_topic:
            print("  retained payload:", msg)
            print("  parsed:", topics.parse_device_error_payload(msg))

    print()
    print("--- 4. keepalive: driving tick() for 120s (broker drop window is ~90s) ---")
    print("  NOTE: the broker's own session view is the more reliable check --")
    print("  watch EMQX for one stable '{}' session over 5+ min.".format(config.DEVICE_ID))
    start = time.ticks_ms()
    drops = 0
    while time.ticks_diff(time.ticks_ms(), start) < 120_000:
        feed_wdt()
        was_connected = mqtt.connected
        mqtt.tick()
        if was_connected and not mqtt.connected:
            drops += 1
            print("  ! disconnect at t+{}s".format(time.ticks_diff(time.ticks_ms(), start) // 1000))
        time.sleep_ms(100)
    print("  done: connected =", mqtt.connected, "-- disconnects during window:", drops)
    print("  (0 disconnects = PINGREQ is holding the session open)")


main()
