"""
Tests for dashboard.state_store's keyed pub/sub DashboardState.
"""

from unittest import mock

from dashboard.state_store import DashboardState


def test_get_returns_default_for_unknown_key():
    state = DashboardState()
    assert state.get("light/lamp") is None
    assert state.get("light/lamp", "fallback") == "fallback"


def test_set_then_get_returns_stored_value():
    state = DashboardState()
    state.set("light/lamp", {"state": "on"})
    assert state.get("light/lamp") == {"state": "on"}


def test_on_update_is_called_with_new_value_on_set():
    state = DashboardState()
    callback = mock.Mock()
    state.on_update("light/lamp", callback)

    state.set("light/lamp", {"state": "on"})

    callback.assert_called_once_with({"state": "on"})


def test_on_update_not_called_for_a_different_key():
    state = DashboardState()
    callback = mock.Mock()
    state.on_update("light/lamp", callback)

    state.set("light/other", {"state": "on"})

    callback.assert_not_called()


def test_multiple_listeners_on_same_key_all_receive_updates():
    state = DashboardState()
    callback_a = mock.Mock()
    callback_b = mock.Mock()
    state.on_update("light/lamp", callback_a)
    state.on_update("light/lamp", callback_b)

    state.set("light/lamp", {"state": "off"})

    callback_a.assert_called_once_with({"state": "off"})
    callback_b.assert_called_once_with({"state": "off"})


def test_unsubscribe_stops_further_callbacks():
    state = DashboardState()
    callback = mock.Mock()
    unsubscribe = state.on_update("light/lamp", callback)

    unsubscribe()
    state.set("light/lamp", {"state": "on"})

    callback.assert_not_called()


def test_unsubscribe_only_removes_the_matching_listener():
    state = DashboardState()
    callback_a = mock.Mock()
    callback_b = mock.Mock()
    unsubscribe_a = state.on_update("light/lamp", callback_a)
    state.on_update("light/lamp", callback_b)

    unsubscribe_a()
    state.set("light/lamp", {"state": "on"})

    callback_a.assert_not_called()
    callback_b.assert_called_once_with({"state": "on"})


def test_unsubscribe_is_safe_to_call_more_than_once():
    state = DashboardState()
    callback = mock.Mock()
    unsubscribe = state.on_update("light/lamp", callback)

    unsubscribe()
    unsubscribe()  # must not raise

    state.set("light/lamp", {"state": "on"})
    callback.assert_not_called()


def test_callback_can_unsubscribe_itself_without_breaking_dispatch_to_others():
    state = DashboardState()
    calls = []

    def self_unsubscribing_callback(value):
        calls.append(("self", value))
        unsubscribe_self()

    def other_callback(value):
        calls.append(("other", value))

    unsubscribe_self = state.on_update("light/lamp", self_unsubscribing_callback)
    state.on_update("light/lamp", other_callback)

    state.set("light/lamp", {"state": "on"})

    assert ("self", {"state": "on"}) in calls
    assert ("other", {"state": "on"}) in calls

    # Second set should only reach the still-subscribed listener.
    calls.clear()
    state.set("light/lamp", {"state": "off"})
    assert calls == [("other", {"state": "off"})]
