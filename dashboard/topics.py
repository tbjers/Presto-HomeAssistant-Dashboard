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
READ_ONLY_DOMAINS = ("sensor",)

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

    # Unknown domain: pass the parsed dict through unvalidated.
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
