# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Local, on-device settings persistence -- distinct from config.py/topics.py's
retained-MQTT screens/tiles contract, which is Node-RED/HA-driven and isn't
something the user can change from the Presto's own touchscreen. Settings
here (corner_style, corner_radius, font_choice) are read/written entirely
locally, via a small JSON file on the device's own flash, and are only ever
changed from dashboard.settings_page.SettingsPage.

Uses `json`, following dashboard/topics.py's own precedent (MicroPython
ships a `json` module, so there's no need for a second `ujson`-based JSON
convention in this codebase).

DEFAULTS reproduces dashboard.theme.CompressoTheme's own class-level
defaults (smooth style, large radius, the existing font5x5 bitmap font).

VALID_FONT_CHOICES must be kept in sync with dashboard.theme.CompressoTheme's
FONT_CHOICES keys and dashboard.settings_page's FONT_CHOICE_ORDER -- adding a
font means updating all three.
"""

import json

from dashboard import corners

VALID_FONT_CHOICES = ("default", "atkinson", "inter")

DEFAULTS = {
    "corner_style": "smooth",
    "corner_radius": "large",
    "font_choice": "default",
}

SETTINGS_PATH = "settings.json"


def _is_valid(key, value):
    if key == "corner_style":
        return value in ("smooth", "blocky")
    if key == "corner_radius":
        return value in corners.RADIUS_CHOICES
    if key == "font_choice":
        return value in VALID_FONT_CHOICES
    return True


def load(path=SETTINGS_PATH):
    """
    Returns a dict with every DEFAULTS key present, overridden by whatever
    was actually persisted at `path`. Never raises, and never returns a
    value a caller couldn't act on: a missing file (first boot), corrupt
    JSON, an unexpected/partial payload, or an out-of-range/unknown value
    for a known key (e.g. a hand-edited or version-skewed settings.json)
    all just fall back to DEFAULTS for the affected keys -- so a bad
    settings file can never block boot *or* crash SettingsPage.setup()
    later (RadioButton/FONT_CHOICE_ORDER.index() would raise on a value
    outside their own valid range).
    """
    settings = dict(DEFAULTS)
    try:
        with open(path) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return settings
    if isinstance(saved, dict):
        settings.update(
            {key: value for key, value in saved.items() if key in DEFAULTS and _is_valid(key, value)}
        )
    return settings


def save(settings, path=SETTINGS_PATH):
    """
    Persists `settings` to `path`, merged over DEFAULTS first so a caller
    passing a partial dict never drops previously-saved keys. Returns the
    merged dict actually written.
    """
    merged = dict(DEFAULTS)
    merged.update(
        {key: value for key, value in settings.items() if key in DEFAULTS and _is_valid(key, value)}
    )
    with open(path, "w") as f:
        json.dump(merged, f)
    return merged
