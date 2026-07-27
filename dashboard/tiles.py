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

from dashboard import grid, palette, topics, weather_icon
from dashboard.modal import LightBrightnessModal


class Tile:
    def __init__(self, region, pens):
        self.region = region
        self._pens = pens
        self._dirty = True  # starts dirty so the first tick always paints

    def draw(self, display, theme):
        raise NotImplementedError()

    def set_state(self, value):
        """Updates cached data only -- does not draw. The caller
        (DashboardPage) is responsible for setting page.needs_update
        afterwards. Subclasses that back a plain (non-Control) tile should
        set self._dirty = True here, but only when the incoming value
        actually differs from what's cached -- see is_dirty()."""

    def is_dirty(self):
        """
        Whether this tile needs to be redrawn. Checked by
        DashboardPage._draw() for plain tiles only -- Control-based tiles
        (ToggleTile, SceneButtonTile, DimmableLightTile) are drawn
        unconditionally by TmOS's own vendored Page._tick() loop instead,
        so dirty-tracking doesn't apply to them.
        """
        return self._dirty

    def mark_clean(self):
        """Called by DashboardPage._draw() after drawing a dirty tile."""
        self._dirty = False

    def mark_dirty(self):
        """Forces this tile to redraw on the next tick, regardless of
        whether its cached data changed -- used when the page becomes
        visible again after being hidden, since the screen may have been
        overwritten by whatever page was shown in between."""
        self._dirty = True


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
        new_value = value.get("value") if value else None
        if new_value != self._value:
            self._value = new_value
            self._dirty = True

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


class WeatherTile(Tile):
    """
    Read-only weather display: MDI condition icon (dashboard.weather_icon,
    vector, monochrome) + temperature + label. No threshold-colored
    background like ValueTile -- weather condition doesn't map to a
    background-color gradient.

    Vector rendering is viable here (unlike it would be for a tile redrawn
    every tick) because this is a plain tile: Part 1's dirty-tracking means
    draw() only runs when the condition/temperature actually changes, which
    for a weather entity is on the order of minutes, not 10x/second.

    Layout is size-specific rather than a single formula, per the project
    owner's direction: the smallest (4x4) tile has no room for an icon
    alongside the temperature, so it drops the icon entirely and matches
    ValueTile's own layout exactly (large value, dimmed unit beside it,
    label pinned to the tile's bottom edge). The two wider sizes (8x4,
    16x6) both put a half-size icon beside a temperature/unit/label block
    that's shifted one grid cell down and over from the icon's own
    (full-size) bounding box, with the label directly beneath that block
    instead of at the tile's bottom edge. Both cases are reached through
    the same `width > height * _wide_aspect_ratio` check that already
    existed for telling wide tiles from square/tall ones -- 8x4 and 16x6
    both clear that threshold, 4x4 doesn't.

    Humidity is optional and only shown in the wide (icon) layout -- when
    present, it's inserted where the label would otherwise sit, and the
    label itself moves down one more grid row to make room. Not supported
    in the compact (4x4) layout, which is deliberately ValueTile-identical
    and has no equivalent "row" to insert one into.
    """

    temperature_rel_scale = 3
    _wide_aspect_ratio = 1.5
    _icon_shrink = 0.5

    def __init__(
        self, region, pens, label, unit="", initial_condition=None, initial_temperature=None,
        initial_humidity=None,
    ):
        super().__init__(region, pens)
        self.label = label
        self.unit = unit
        self._condition = initial_condition
        self._temperature = initial_temperature
        self._humidity = initial_humidity

    def set_state(self, value):
        condition = value.get("condition") if value else None
        temperature = value.get("temperature") if value else None
        humidity = value.get("humidity") if value else None
        new_state = (condition, temperature, humidity)
        if new_state != (self._condition, self._temperature, self._humidity):
            self._condition, self._temperature, self._humidity = new_state
            self._dirty = True

    def draw(self, display, theme):
        x, y, width, height = self.region
        _draw_bg(display, self._pens, self.region, palette.GRAY_900)

        if width > height * self._wide_aspect_ratio:
            self._draw_wide(display, theme, x, y, height)
        else:
            self._draw_compact(display, theme, x, y, height)

    def _draw_compact(self, display, theme, x, y, height):
        """No icon -- used for the smallest (4x4) tile, where there isn't
        room for one alongside the temperature. Deliberately identical to
        ValueTile.draw()'s layout (large value, dimmed unit beside it,
        label at the tile's bottom edge), not just visually similar."""
        text_x = x + theme.padding
        value_y = y + theme.padding

        if self._temperature is not None:
            temp_text = str(round(self._temperature))
            display.set_pen(self._pens.get(palette.GRAY_200))
            theme.text(display, temp_text, text_x, value_y, rel_scale=self.temperature_rel_scale)

            if self.unit:
                temp_width, _ = theme.measure_text(
                    display, temp_text, rel_scale=self.temperature_rel_scale
                )
                unit_text = "°" + self.unit
                display.set_pen(self._pens.get(palette.GRAY_600))
                # Matches ValueTile's exact value-to-unit gap (see its
                # draw()): offset is relative to the value's own draw
                # position (text_x), same as ValueTile's is relative to
                # its value's draw position (x + theme.padding) -- both
                # reduce to value_width + 4 - theme.padding from there.
                theme.text(
                    display, unit_text, text_x + temp_width + 4 - theme.padding, value_y, rel_scale=1
                )

        display.set_pen(self._pens.get(palette.GRAY_600))
        theme.text(display, self.label, text_x, y + height - theme.padding - 10, rel_scale=1)

    def _draw_wide(self, display, theme, x, y, height):
        """Icon beside a temperature/unit/label block -- used for 8x4 and
        16x6, the two sizes with enough width to fit both."""
        icon_box_size = int(height - theme.padding * 2)
        icon_box_x = x + theme.padding
        icon_box_y = y + theme.padding

        # The icon is drawn at half that box's size, centered within it,
        # rather than filling it -- confirmed by the project owner as the
        # preferred look once the temperature/unit/label moved to its own
        # offset block below instead of sitting flush against the icon.
        icon_size = int(icon_box_size * self._icon_shrink)
        icon_x = icon_box_x + (icon_box_size - icon_size) // 2
        icon_y = icon_box_y + (icon_box_size - icon_size) // 2
        # Dimmer than the temperature/label text (GRAY_200) -- at GRAY_200
        # the icon read as "really, really bright" against the tile's dark
        # (GRAY_900) background, per the project owner.
        weather_icon.draw(
            display, self._condition, icon_x, icon_y, icon_size, self._pens.get(palette.GRAY_500)
        )

        # One grid cell's worth of pixels, in either direction -- matches
        # how dashboard.grid.cell_region itself steps between adjacent
        # columns/rows (tile size + gap), not just the bare cell size.
        # Reference width is the fixed 480px display width (this app always
        # boots full_res=True), the same hardcoded reference
        # dashboard/theme.py's CompressoTheme.setup() already uses for
        # systray_height.
        grid_step = round(grid.tile_size(480) + theme.padding)

        # The temperature/unit/label block anchors one grid cell down and
        # over from where the icon's own (full-size) bounding box ended.
        text_x = icon_box_x + icon_box_size + theme.padding
        temp_y = icon_box_y + grid_step

        label_y = temp_y
        if self._temperature is not None:
            temp_text = str(round(self._temperature))
            display.set_pen(self._pens.get(palette.GRAY_200))
            theme.text(display, temp_text, text_x, temp_y, rel_scale=self.temperature_rel_scale)
            temp_width, temp_height = theme.measure_text(
                display, temp_text, rel_scale=self.temperature_rel_scale
            )

            if self.unit:
                # Matches ValueTile's exact value-to-unit gap -- see
                # _draw_compact's equivalent line for the derivation.
                unit_text = "°" + self.unit
                display.set_pen(self._pens.get(palette.GRAY_600))
                theme.text(
                    display, unit_text, text_x + temp_width + 6 - theme.padding, temp_y, rel_scale=1
                )

            # +4 to clear the value's own descender/baseline the same way
            # ValueTile's bottom-pinned label already does, plus 6 more on
            # top of that -- the project owner asked for a bit more
            # breathing room between the temperature and the label here
            # specifically (this gap doesn't exist in ValueTile at all,
            # since its label is pinned to the tile's bottom edge instead
            # of sitting directly under the value).
            label_y = temp_y + temp_height + 4 + 6

        if self._humidity is not None:
            # Humidity takes the row the label would otherwise have used;
            # the label itself moves down one grid row (same grid_step
            # used to anchor the temperature block above) to make room --
            # per the project owner's instructions. Drawn in GRAY_200 (the
            # same bright color as the temperature value), not the dimmed
            # GRAY_600 the label/unit use.
            humidity_text = "{}% HUMIDITY".format(round(self._humidity))
            display.set_pen(self._pens.get(palette.GRAY_200))
            theme.text(display, humidity_text, text_x, label_y, rel_scale=1)
            label_y += grid_step

        display.set_pen(self._pens.get(palette.GRAY_600))
        theme.text(display, self.label, text_x, label_y, rel_scale=1)


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
        self._last_rendered = None  # (time_text, date_text), or None before the first draw

    def _current_text(self):
        t = self._os.localtime()
        month, mday, hour, minute, weekday = t[1], t[2], t[3], t[4], t[6]
        time_text = "{:0>2}:{:0>2}".format(hour, minute)
        date_text = "{}, {:0>2}.{:0>2}.".format(self.weekdays[weekday], mday, month)
        return time_text, date_text

    def is_dirty(self):
        """Driven by the RTC, not set_state() -- dirty whenever the
        minute/date actually displayed would change, not on every tick."""
        return self._current_text() != self._last_rendered

    def mark_dirty(self):
        self._last_rendered = None

    def mark_clean(self):
        self._last_rendered = self._current_text()

    def draw(self, display, theme):
        x, y, width, height = self.region
        _draw_bg(display, self._pens, self.region, palette.GRAY_900)

        time_text, date_text = self._current_text()

        display.set_pen(self._pens.get(palette.GRAY_200))
        theme.text(display, time_text, x + theme.padding, y + theme.padding, rel_scale=3)

        display.set_pen(self._pens.get(palette.GRAY_600))
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
