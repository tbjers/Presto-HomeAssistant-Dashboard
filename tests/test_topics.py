"""
Tests for dashboard.topics — the MQTT topic/payload contract.
"""

import json

import pytest

from dashboard import topics


class TestTopicBuilders:
    def test_state_topic(self):
        assert topics.state_topic("light", "living_room_lamp") == "presto/light/living_room_lamp/state"

    def test_set_topic(self):
        assert topics.set_topic("light", "living_room_lamp") == "presto/light/living_room_lamp/set"

    def test_state_wildcard(self):
        assert topics.state_wildcard() == "presto/+/+/state"

    def test_device_status_topic(self):
        assert topics.device_status_topic("presto-office") == "presto/device/presto-office/status"

    def test_bridge_status_topic_constant(self):
        assert topics.BRIDGE_STATUS_TOPIC == "presto/bridge/status"


class TestParseTopic:
    def test_parses_state_topic(self):
        assert topics.parse_topic("presto/light/lamp/state") == ("light", "lamp", "state")

    def test_parses_set_topic(self):
        assert topics.parse_topic("presto/switch/fan/set") == ("switch", "fan", "set")

    def test_accepts_bytes(self):
        assert topics.parse_topic(b"presto/light/lamp/state") == ("light", "lamp", "state")

    def test_rejects_wrong_root(self):
        assert topics.parse_topic("other/light/lamp/state") is None

    def test_rejects_too_few_segments(self):
        assert topics.parse_topic("presto/light/lamp") is None

    def test_rejects_too_many_segments(self):
        assert topics.parse_topic("presto/light/lamp/state/extra") is None

    def test_rejects_unknown_kind(self):
        assert topics.parse_topic("presto/light/lamp/status") is None

    def test_rejects_empty_slug(self):
        assert topics.parse_topic("presto/light//state") is None

    def test_does_not_match_device_status_topic(self):
        assert topics.parse_topic("presto/device/presto-office/status") is None

    def test_does_not_match_bridge_status_topic(self):
        assert topics.parse_topic(topics.BRIDGE_STATUS_TOPIC) is None


class TestParseStatePayload:
    def test_valid_switch_payload(self):
        raw = json.dumps({"state": "on"}).encode()
        assert topics.parse_state_payload("switch", raw) == {"state": "on"}

    def test_valid_light_payload_with_brightness(self):
        raw = json.dumps({"state": "on", "brightness": 128}).encode()
        assert topics.parse_state_payload("light", raw) == {"state": "on", "brightness": 128}

    def test_valid_light_payload_with_null_brightness(self):
        raw = json.dumps({"state": "off", "brightness": None}).encode()
        assert topics.parse_state_payload("light", raw) == {"state": "off", "brightness": None}

    def test_light_payload_with_non_numeric_brightness_is_rejected(self):
        raw = json.dumps({"state": "on", "brightness": "bright"}).encode()
        assert topics.parse_state_payload("light", raw) is None

    def test_valid_sensor_payload(self):
        raw = json.dumps({"value": 21.5, "unit": "°C"}).encode()
        assert topics.parse_state_payload("sensor", raw) == {"value": 21.5, "unit": "°C"}

    def test_sensor_payload_missing_value_is_rejected(self):
        raw = json.dumps({"unit": "°C"}).encode()
        assert topics.parse_state_payload("sensor", raw) is None

    def test_switch_payload_with_invalid_state_is_rejected(self):
        raw = json.dumps({"state": "maybe"}).encode()
        assert topics.parse_state_payload("switch", raw) is None

    def test_switch_payload_missing_state_is_rejected(self):
        raw = json.dumps({}).encode()
        assert topics.parse_state_payload("switch", raw) is None

    def test_accepts_str_as_well_as_bytes(self):
        raw = json.dumps({"state": "on"})
        assert topics.parse_state_payload("switch", raw) == {"state": "on"}

    def test_malformed_json_returns_none_not_raises(self):
        assert topics.parse_state_payload("switch", b"{not json") is None

    def test_empty_payload_returns_none(self):
        assert topics.parse_state_payload("switch", b"") is None

    def test_non_object_json_returns_none(self):
        assert topics.parse_state_payload("switch", b"42") is None
        assert topics.parse_state_payload("switch", b'"on"') is None
        assert topics.parse_state_payload("switch", b"[1, 2]") is None

    def test_unknown_domain_passes_through_dict_unvalidated(self):
        raw = json.dumps({"anything": True}).encode()
        assert topics.parse_state_payload("weather", raw) == {"anything": True}


class TestParseAvailabilityPayload:
    def test_online(self):
        assert topics.parse_availability_payload(b"online") is True

    def test_offline(self):
        assert topics.parse_availability_payload(b"offline") is False

    def test_accepts_str(self):
        assert topics.parse_availability_payload("online") is True

    def test_unrecognized_returns_none(self):
        assert topics.parse_availability_payload(b"unknown") is None
        assert topics.parse_availability_payload(b"") is None


class TestFormatCommands:
    def test_format_light_command_on_without_brightness(self):
        payload = json.loads(topics.format_light_command(True))
        assert payload == {"state": "on"}

    def test_format_light_command_off(self):
        payload = json.loads(topics.format_light_command(False))
        assert payload == {"state": "off"}

    def test_format_light_command_with_brightness(self):
        payload = json.loads(topics.format_light_command(True, brightness=200))
        assert payload == {"state": "on", "brightness": 200}

    def test_format_switch_command(self):
        assert json.loads(topics.format_switch_command(True)) == {"state": "on"}
        assert json.loads(topics.format_switch_command(False)) == {"state": "off"}

    def test_format_scene_command_is_empty_object(self):
        assert json.loads(topics.format_scene_command()) == {}

    def test_format_commands_return_bytes(self):
        assert isinstance(topics.format_light_command(True), bytes)
        assert isinstance(topics.format_switch_command(True), bytes)
        assert isinstance(topics.format_scene_command(), bytes)

    def test_round_trip_light_command_through_parse_state_payload(self):
        # format_* produces a /set command shape; parse_state_payload targets
        # /state, but light's {"state": ...} shape is shared, so a round
        # trip through the light validator should still accept it.
        raw = topics.format_light_command(True, brightness=50)
        assert topics.parse_state_payload("light", raw) == {"state": "on", "brightness": 50}
