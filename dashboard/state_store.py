"""
Keyed pub/sub state store, adapted from compresto's
`on_update(callback) -> unsubscribe_fn` / `_dispatch_event("update")` pattern
(which had a handful of named clients) into a store keyed by many independent
entities. `key` is `"{domain}/{slug}"`, matching the MQTT topic contract's
addressing, so `mqtt_client.py` can update state purely from parsed topic
parts without knowing about tiles, and `tiles.py`/`page.py` can subscribe by
the same key without knowing about MQTT.
"""


class DashboardState:
    def __init__(self):
        self._values = {}
        self._listeners = {}

    def get(self, key: str, default=None):
        return self._values.get(key, default)

    def set(self, key: str, value) -> None:
        self._values[key] = value
        for callback in list(self._listeners.get(key, ())):
            callback(value)

    def on_update(self, key: str, callback):
        """Registers callback(value) for updates to `key`; returns an
        unsubscribe function."""
        self._listeners.setdefault(key, []).append(callback)

        def unsubscribe():
            listeners = self._listeners.get(key)
            if listeners is not None and callback in listeners:
                listeners.remove(callback)

        return unsubscribe
