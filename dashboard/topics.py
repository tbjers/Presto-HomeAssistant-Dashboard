# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
MQTT topic/payload contract — the single source of truth for the wire format
between this firmware and the Node-RED bridge. Both mqtt_client.py and
tiles.py/page.py import from here rather than hand-building topic strings or
parsing JSON ad hoc. See the project plan's "MQTT topic & payload contract"
section for the full table this implements.

Note: deliberately avoids `X | None`-style union type hints, since annotation
expressions are evaluated at function-definition time (not lazily) and it's
not worth risking MicroPython compatibility across versions for a hint.
"""

import json

TOPIC_ROOT = "presto"

STATE_KIND = "state"
SET_KIND = "set"

# Domains that only ever produce a /set command (no persisted /state topic).
TRIGGER_DOMAINS = ("scene", "script")

# Domains that only ever publish /state (no /set — read-only).
READ_ONLY_DOMAINS = ("sensor", "weather")

BRIDGE_STATUS_TOPIC = "{}/bridge/status".format(TOPIC_ROOT)


def _entity_topic(domain, slug, kind):
    return "{}/{}/{}/{}".format(TOPIC_ROOT, domain, slug, kind)


def state_topic(domain, slug):
    return _entity_topic(domain, slug, STATE_KIND)


def set_topic(domain, slug):
    return _entity_topic(domain, slug, SET_KIND)


def state_wildcard():
    """Subscription filter matching every entity's /state topic in one go."""
    return "{}/+/+/{}".format(TOPIC_ROOT, STATE_KIND)


def device_status_topic(device_id):
    return "{}/device/{}/status".format(TOPIC_ROOT, device_id)


def device_config_topic(device_id):
    return "{}/device/{}/config".format(TOPIC_ROOT, device_id)


def device_error_topic(device_id):
    """
    Diagnostic error/fault channel for this device. The firmware publishes
    here *retained* and never publishes an empty payload -- so the topic is
    only ever cleared by an explicit zero-length retained publish from
    Node-RED (manually, or from a flow / HA button). That's the whole
    "errors are never cleared unless done in Node-RED" contract: it needs
    no mechanism beyond the firmware simply never blanking it.

    A single retained topic holds only the *latest* error; the durable
    "every error ever" log is Node-RED's job (subscribe to
    presto/device/+/error and append each message to a persistent store).
    """
    return "{}/device/{}/error".format(TOPIC_ROOT, device_id)


# Error severities carried in a device-error payload's "level" field.
ERROR_LEVEL_WARNING = "warning"
ERROR_LEVEL_FATAL = "fatal"


def format_device_error_payload(boot_id, seq, level, context, message):
    """
    Builds the JSON body for device_error_topic(). Deliberately carries no
    timestamp: the device clock is unreliable before NTP and uses a
    2000-based epoch, so Node-RED's own ingest time is authoritative.
    `seq` is a monotonic per-boot counter -- it orders errors within a boot
    and, combined with `boot_id`, lets Node-RED spot gaps where the
    firmware's bounded outbound queue dropped one.
    """
    return json.dumps(
        {
            "boot_id": boot_id,
            "seq": seq,
            "level": level,
            "context": context,
            "message": message,
        }
    ).encode()


def parse_device_error_payload(raw):
    """
    Decodes a device-error payload back to a dict. Never raises -- returns
    None on anything malformed or missing a required field.
    """
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("boot_id", "seq", "level", "context", "message"):
        if key not in payload:
            return None
    return payload


def parse_topic(topic):
    """
    Parses an entity topic of the form presto/<domain>/<slug>/<kind> into
    (domain, slug, kind). Returns None for anything that doesn't match this
    shape — including the fixed device/bridge availability topics, which
    callers should check for separately via device_status_topic()/
    BRIDGE_STATUS_TOPIC, since they don't follow the domain/slug/kind shape.
    """
    if isinstance(topic, bytes):
        topic = topic.decode()
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != TOPIC_ROOT:
        return None
    _, domain, slug, kind = parts
    if not domain or not slug:
        return None
    if kind not in (STATE_KIND, SET_KIND):
        return None
    return domain, slug, kind


def parse_state_payload(domain, raw):
    """
    json.loads with light validation against the expected shape for
    `domain`. Never raises — returns None on malformed/unexpected input so a
    single bad message can't crash the MQTT task.
    """
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None

    if domain in ("light", "switch"):
        if payload.get("state") not in ("on", "off"):
            return None
        if domain == "light":
            brightness = payload.get("brightness")
            if brightness is not None and not isinstance(brightness, (int, float)):
                return None
        return payload

    if domain == "sensor":
        if "value" not in payload:
            return None
        return payload

    if domain == "weather":
        if not isinstance(payload.get("condition"), str):
            return None
        return payload

    # Unknown domain: pass the parsed dict through unvalidated.
    return payload


def parse_config_payload(raw):
    """
    json.loads with light validation of the envelope shape --
    {"screens": [{"title": ..., "tiles": [...]}, ...]} -- the same
    "validate the envelope, trust the contents" style as
    parse_state_payload. Individual tile dicts inside "tiles" are NOT
    validated here: they're trusted the same way config.py's hand-authored
    DEFAULT_SCREENS already is, so a malformed tile spec fails the same way
    a config.py typo does today (a KeyError from the relevant tile builder
    in dashboard/page.py) rather than here. Never raises -- returns None on
    anything malformed so a single bad message can't crash the MQTT task.
    """
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None

    screens = payload.get("screens")
    if not isinstance(screens, list) or not screens:
        return None
    for screen in screens:
        if not isinstance(screen, dict) or not isinstance(screen.get("tiles"), list):
            return None

    return payload


def parse_availability_payload(raw):
    """Decodes a plain "online"/"offline" LWT payload (not JSON). Returns
    True/False, or None if unrecognized."""
    if isinstance(raw, bytes):
        raw = raw.decode()
    if raw == "online":
        return True
    if raw == "offline":
        return False
    return None


def format_light_command(state, brightness=None):
    payload = {"state": "on" if state else "off"}
    if brightness is not None:
        payload["brightness"] = brightness
    return json.dumps(payload).encode()


def format_switch_command(state):
    return json.dumps({"state": "on" if state else "off"}).encode()


def format_scene_command():
    return json.dumps({}).encode()
