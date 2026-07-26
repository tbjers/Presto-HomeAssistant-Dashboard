# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

# ValueTile/DateTimeTile behavior ported from compresto
# (https://git.hack-hro.de/kmohrf/compresto), Copyright (C) Konrad Mohrfeldt,
# licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the "Licensing" section of CLAUDE.md.

"""
Tile primitives on top of TmOS's Region/Control model.

Compresto's Component/Tile draw and flush themselves directly; TmOS instead
has Page._tick() iterate self._controls (each a Control with
process_touch_state/draw), call Page._draw() for non-interactive content,
then flush the whole page region once via window_manager.update_display()
-- confirmed from source, TmOS handles flushing automatically, unlike
compresto's manual per-component partial_update(). Tile.draw(display,
theme) deliberately matches Control.draw(self, display, theme)'s real
signature so both Control-based tiles (drawn by TmOS's own Page._tick loop)
and plain tiles (drawn directly by DashboardPage._draw()) share one
contract.
"""

import time

from tmos_ui import Control, MomentaryButton

from dashboard import palette, topics
from dashboard.modal import LightBrightnessModal


class Tile:
    def __init__(self, region, pens):
        self.region = region
        self._pens = pens

    def draw(self, display, theme):
        raise NotImplementedError()

    def set_state(self, value):
        """Updates cached data only -- does not draw. The caller
        (DashboardPage) is responsible for setting page.needs_update
        afterwards."""


def _draw_bg(display, pens, region, color):
    x, y, width, height = region
    display.set_pen(pens.get(color))
    display.rectangle(x, y, width, height)


class ValueTile(Tile):
    """
    Read-only numeric/text display: big value + small uppercase label,
    threshold-colored background. Used for the sensor domain.

    Ported from compresto's ValueTile/TemperatureTile pattern: thresholds
    map to a (background, value_text, description_text) triple (see
    dashboard.palette's *_SCALE constants), not a single color, so text
    stays legible against a bright/saturated background rather than a flat
    neutral.
    """

    value_rel_scale = 3

    def __init__(self, region, pens, label, unit="", thresholds=None, initial_value=None):
        super().__init__(region, pens)
        self.label = label
        self.unit = unit
        self.thresholds = thresholds or []
        self._value = initial_value

    def set_state(self, value):
        self._value = value.get("value") if value else None

    def draw(self, display, theme):
        x, y, width, height = self.region
        bg, value_color, desc_color = palette.color_for_thresholds(
            self._value, self.thresholds, default=palette.NEUTRAL_SCALE
        )
        _draw_bg(display, self._pens, self.region, bg)

        value_text = str(self._value) if self._value is not None else "-"
        display.set_pen(self._pens.get(value_color))
        theme.text(
            display, value_text, x + theme.padding, y + theme.padding, rel_scale=self.value_rel_scale
        )

        if self.unit:
            value_width, _ = theme.measure_text(display, value_text, rel_scale=self.value_rel_scale)
            unit_text = "°" + self.unit
            display.set_pen(self._pens.get(desc_color))
            theme.text(
                display, unit_text, x + value_width + 4, y + theme.padding,
                rel_scale=1,
            )

        display.set_pen(self._pens.get(desc_color))
        theme.text(display, self.label, x + theme.padding, y + height - theme.padding - 10, rel_scale=1)


class DateTimeTile(Tile):
    """
    HH:MM + weekday/date, driven by the device RTC only (via
    os.localtime()) -- no HA/MQTT dependency, no set_state() needed.

    Ported from compresto's DateTimeTile, minus the "animated colon while
    working" behavior (no equivalent concept here).

    Note: OS.localtime() returns time.gmtime(...) directly. CPython's
    time.gmtime() returns a 9-field struct_time (with tm_isdst); real
    MicroPython's returns an 8-tuple without it. Indexing rather than a
    full positional unpack keeps this correct on both, since the first 7
    fields (year, month, mday, hour, minute, second, weekday) share the
    same order and Monday=0 convention on both platforms.
    """

    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

    def __init__(self, region, pens, os):
        super().__init__(region, pens)
        self._os = os

    def draw(self, display, theme):
        x, y, width, height = self.region
        _draw_bg(display, self._pens, self.region, palette.GRAY_900)

        t = self._os.localtime()
        month, mday, hour, minute, weekday = t[1], t[2], t[3], t[4], t[6]

        display.set_pen(self._pens.get(palette.GRAY_200))
        time_text = "{:0>2}:{:0>2}".format(hour, minute)
        theme.text(display, time_text, x + theme.padding, y + theme.padding, rel_scale=3)

        display.set_pen(self._pens.get(palette.GRAY_600))
        date_text = "{}, {:0>2}.{:0>2}.".format(self.weekdays[weekday], mday, month)
        theme.text(display, date_text, x + theme.padding, y + height - theme.padding - 10, rel_scale=1)


class ToggleTile(Tile, Control):
    """
    A tile for a plain on/off light or switch. Tap toggles directly via
    MQTT, optimistically -- the next retained state message (this change or
    any other) always overwrites whatever the tile is showing; there is no
    local pending/revert state machine.

    Wraps a MomentaryButton for touch geometry/event semantics (reusing its
    is_within-gated press/release/cancel handling rather than reimplementing
    it), but overrides draw() to paint compresto-style tile chrome instead
    of the button's default frame/title.
    """

    def __init__(self, region, pens, domain, slug, label, mqtt, initial_state=None):
        Tile.__init__(self, region, pens)
        self.domain = domain
        self.slug = slug
        self.label = label
        self._mqtt = mqtt
        self._state = initial_state  # True/False/None (unknown)
        self._button = MomentaryButton(region)
        self._button.on_button_up = self._toggle

    def process_touch_state(self, touch):
        self._button.process_touch_state(touch)

    def set_state(self, value):
        state = value.get("state") if value else None
        self._state = {"on": True, "off": False}.get(state)

    def _toggle(self):
        new_state = not self._state if self._state is not None else True
        payload = (
            topics.format_light_command(new_state)
            if self.domain == "light"
            else topics.format_switch_command(new_state)
        )
        self._mqtt.publish(topics.set_topic(self.domain, self.slug), payload)

    def draw(self, display, theme):
        x, y, width, height = self.region
        is_on = self._state is True
        bg = palette.GREEN_400 if is_on else palette.GRAY_900
        label_color = palette.GREEN_900 if is_on else palette.GRAY_600

        _draw_bg(display, self._pens, self.region, bg)
        display.set_pen(self._pens.get(label_color))
        theme.text(display, self.label, x + theme.padding, y + height - theme.padding - 10, rel_scale=1)


class SceneButtonTile(Tile, Control):
    """
    A momentary trigger tile for a scene/script. Tap publishes an empty
    command and shows a brief local flash -- no state to track, and no MQTT
    confirmation needed since scenes/scripts are stateless triggers.
    """

    FLASH_DURATION_MS = 400

    def __init__(self, region, pens, domain, slug, label, mqtt):
        Tile.__init__(self, region, pens)
        self.domain = domain
        self.slug = slug
        self.label = label
        self._mqtt = mqtt
        self._button = MomentaryButton(region)
        self._button.on_button_up = self._trigger
        self._flash_started_at = None

    def process_touch_state(self, touch):
        self._button.process_touch_state(touch)

    def _trigger(self):
        self._mqtt.publish(topics.set_topic(self.domain, self.slug), topics.format_scene_command())
        self._flash_started_at = time.ticks_ms()

    # Number of discrete steps the fade is quantized to. Keeps the number of
    # distinct interpolated pens PenCache will ever create for this tile
    # bounded (FLASH_STEPS + 1 per color, forever) rather than one new pen
    # per redraw tick -- see palette.lerp_color's docstring for why that
    # matters (pens are never freed, and PicoGraphics may cap distinct pens).
    FLASH_STEPS = 4

    def _flash_fraction(self):
        """1.0 = just triggered (full amber), decaying to 0.0 (gray) over
        FLASH_DURATION_MS, quantized to FLASH_STEPS discrete values."""
        if self._flash_started_at is None:
            return 0.0
        elapsed = time.ticks_diff(time.ticks_ms(), self._flash_started_at)
        if elapsed >= self.FLASH_DURATION_MS:
            self._flash_started_at = None
            return 0.0
        raw_fraction = 1.0 - (elapsed / self.FLASH_DURATION_MS)
        return round(raw_fraction * self.FLASH_STEPS) / self.FLASH_STEPS

    def draw(self, display, theme):
        x, y, width, height = self.region
        fraction = self._flash_fraction()
        bg = palette.lerp_color(palette.GRAY_900, palette.AMBER_400, fraction)
        label_color = palette.lerp_color(palette.GRAY_600, palette.AMBER_900, fraction)

        _draw_bg(display, self._pens, self.region, bg)
        display.set_pen(self._pens.get(label_color))
        theme.text(display, self.label, x + theme.padding, y + height - theme.padding - 10, rel_scale=1)


class DimmableLightTile(Tile, Control):
    """
    A tile for a dimmable light. Tap opens a modal with brightness control
    (dashboard.modal.LightBrightnessModal) instead of toggling directly.
    """

    def __init__(
        self, region, pens, domain, slug, label, mqtt, window_manager,
        initial_state=None, initial_brightness=None,
    ):
        Tile.__init__(self, region, pens)
        self.domain = domain
        self.slug = slug
        self.label = label
        self._mqtt = mqtt
        self._window_manager = window_manager
        self._state = initial_state
        self._brightness = initial_brightness
        self._button = MomentaryButton(region)
        self._button.on_button_up = self._open_modal

    def process_touch_state(self, touch):
        self._button.process_touch_state(touch)

    def set_state(self, value):
        state = value.get("state") if value else None
        self._state = {"on": True, "off": False}.get(state)
        self._brightness = value.get("brightness") if value else None

    def _open_modal(self):
        modal = LightBrightnessModal(
            self.domain, self.slug, self.label, self._mqtt, self._pens,
            initial_brightness=self._brightness,
        )
        self._window_manager.show_modal_page(modal)

    def draw(self, display, theme):
        x, y, width, height = self.region
        is_on = self._state is True
        bg = palette.GREEN_400 if is_on else palette.GRAY_900
        label_color = palette.GREEN_900 if is_on else palette.GRAY_600

        _draw_bg(display, self._pens, self.region, bg)
        display.set_pen(self._pens.get(label_color))
        theme.text(display, self.label, x + theme.padding, y + height - theme.padding - 10, rel_scale=1)
