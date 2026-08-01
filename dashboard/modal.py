# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Detail modals for tiles needing more than a toggle (v1: dimmable-light
brightness).

TmOS has no dedicated ModalPage class -- confirmed from source:
WindowManager.show_modal_page(page)/clear_modal_page() work with any Page,
giving it the full screen region. TmOS's own examples/09_modal_pages.py
demonstrates the convention of a close button in the top-right calling
window_manager.clear_modal_page; DetailModalPage follows that same
convention as a reusable base.

TmOS also has no slider control -- confirmed from source: Control
subclasses are limited to MomentaryButton/LatchingButton/RadioButton/
SystrayPageButton, none of which track a continuous drag value.
SliderControl is built from scratch here, modeled directly on
_Button/MomentaryButton's own touch handling (touch.state/touch.x/touch.y,
is_within()) rather than guessed at.
"""

from picovector import ANTIALIAS_BEST, PicoVector, Polygon, Transform

from tmos import Region
from tmos_ui import Control, MomentaryButton, StaticPage, is_within

from dashboard import grid, icons, palette, topics


def _clamp(value, low, high):
    return max(low, min(high, value))


class SliderControl(Control):
    """
    A horizontal drag-value control.

    Touch must START within the control's region (mirrors MomentaryButton's
    is_within-gated activation) -- once dragging, the value follows
    touch.x, clamped to the region's width, so the finger can drift outside
    the region without the value jumping.

    on_change(value) fires on every tick while dragging, for live visual
    feedback only. Callers must NOT publish over MQTT from this -- it fires
    once per touch-poll tick and would flood the broker with a message per
    pixel of drag.

    on_commit(value) fires exactly once, when the touch is released -- this
    is the intended point for a caller to actually act on the final value.
    """

    on_change = None
    on_commit = None

    def __init__(self, region: Region, min_value, max_value, initial_value, pens):
        self.region = region
        self.min_value = min_value
        self.max_value = max_value
        self.value = _clamp(initial_value, min_value, max_value)
        self._pens = pens  # dashboard.palette.PenCache, handed in at construction
        self._is_dragging = False
        self._was_touch_active = False

    def process_touch_state(self, touch):
        touch_active = touch.state
        touch_active_inside = touch_active and is_within(self.region, touch.x, touch.y)
        # A "fresh" press (not a continuation of an already-active touch) is
        # required to start a drag -- otherwise a touch that started outside
        # the slider and drags in would be silently grabbed mid-motion.
        fresh_press = touch_active and not self._was_touch_active
        self._was_touch_active = touch_active

        if not self._is_dragging:
            if fresh_press and touch_active_inside:
                self._is_dragging = True
                self._update_value(touch)
            return

        if touch_active:
            self._update_value(touch)
        else:
            self._is_dragging = False
            self._event("on_commit", self.value)

    def _update_value(self, touch):
        fraction = _clamp((touch.x - self.region.x) / self.region.width, 0.0, 1.0)
        self.value = self.min_value + fraction * (self.max_value - self.min_value)
        self._event("on_change", self.value)

    def draw(self, display, theme):
        x, y, width, height = self.region

        display.set_pen(self._pens.get(palette.GRAY_800))
        display.rectangle(x, y, width, height)

        span = self.max_value - self.min_value
        fraction = 0.0 if span == 0 else (self.value - self.min_value) / span
        fill_width = round(width * fraction)
        if fill_width > 0:
            display.set_pen(self._pens.get(palette.AMBER_400))
            display.rectangle(x, y, fill_width, height)

        display.set_pen(self._pens.get(palette.WHITE))
        handle_radius = height // 2
        display.circle(x + fill_width, y + handle_radius, handle_radius)


# Fixed corner radius for VerticalSliderControl's track/fill -- deliberately
# less than a full pill (width // 2) to avoid an unverified set_clip-based
# fill approach (no precedent anywhere else in this codebase for clipping
# inside a single Control.draw()). Tune on-device.
_VERTICAL_TRACK_CORNER_RADIUS = 20


class VerticalSliderControl(SliderControl):
    """
    A vertical variant of SliderControl: no drag handle, rounded track/fill
    corners. See SliderControl's docstring for the shared touch/drag/
    on_change/on_commit contract -- only the touch-axis mapping and drawing
    differ here.

    Touch is inverted relative to a plain y-coordinate: near the top of the
    region sets a higher value, near the bottom sets a lower value, and the
    fill grows upward from the bottom -- the usual vertical fader
    convention.

    `is_on` is plain external state (default True) -- the owning page must
    set it (see LightBrightnessModal._update, mirroring PowerButton's own
    is_on) before draw() runs each tick. It only affects the fill color:
    GREEN_400 when on, a slightly-brighter-than-track gray (GRAY_700 vs the
    track's GRAY_800) when off, so the fill doesn't read as "still on" once
    the light has been powered off from the slider's own power button.

    The PicoVector instance and the track's Polygon (fixed geometry once
    region is set) are built once and cached rather than rebuilt every
    draw() call: a modal page's controls are redrawn unconditionally on
    every run-loop tick (WindowManager.show_modal_page's task has no
    execution_frequency, and OS.add_task's docstring states "if omitted, it
    will be called each tick"), unlike a normal page's needs_update-gated
    redraws. Only the fill polygon, whose height varies, is rebuilt per
    frame.
    """

    def __init__(self, region: Region, min_value, max_value, initial_value, pens):
        super().__init__(region, min_value, max_value, initial_value, pens)
        self.is_on = True  # plain external state, see PowerButton's own is_on
        self._vector = None
        self._track_polygon = None

    def _update_value(self, touch):
        fraction = _clamp(
            (self.region.y + self.region.height - touch.y) / self.region.height, 0.0, 1.0
        )
        self.value = self.min_value + fraction * (self.max_value - self.min_value)
        self._event("on_change", self.value)

    def draw(self, display, theme):
        x, y, width, height = self.region

        if self._vector is None:
            self._vector = PicoVector(display)
            self._vector.set_antialiasing(ANTIALIAS_BEST)
            self._vector.set_transform(Transform())
        if self._track_polygon is None:
            self._track_polygon = Polygon()
            self._track_polygon.rectangle(
                x, y, width, height, corners=(_VERTICAL_TRACK_CORNER_RADIUS,) * 4
            )

        display.set_pen(self._pens.get(palette.GRAY_800))
        self._vector.draw(self._track_polygon)

        span = self.max_value - self.min_value
        fraction = 0.0 if span == 0 else (self.value - self.min_value) / span
        fill_height = round(height * fraction)
        if fill_height > 0:
            # A separately-sized rounded rect anchored to the bottom, not a
            # crop of the track -- at fraction=1.0 it exactly coincides with
            # the track (same x/width/radius). Its own radius is clamped so
            # it never exceeds half its own (possibly small) height.
            fill_radius = min(_VERTICAL_TRACK_CORNER_RADIUS, fill_height / 2)
            fill = Polygon()
            fill.rectangle(
                x, y + height - fill_height, width, fill_height, corners=(fill_radius,) * 4
            )
            fill_color = palette.GREEN_400 if self.is_on else palette.GRAY_700
            display.set_pen(self._pens.get(fill_color))
            self._vector.draw(fill)


class PowerButton(MomentaryButton):
    """
    A MomentaryButton variant drawing a solid state-tinted rounded-rect
    background plus a centered mdiPower vector icon, instead of _Button's
    themed frame + text title. Deliberately mirrors DimmableLightTile's own
    on/off coloring (GREEN_400/GREEN_900 on, GRAY_900/GRAY_600 off) so the
    modal's power control reads as the same signal as the tile it opened
    from, not a generic themed button.

    `is_on` is plain external state -- the owning page must set it (see
    LightBrightnessModal._update) before this control's draw() runs each
    tick. Touch handling itself (on_button_down/up/cancel) is inherited
    unmodified from MomentaryButton and only drives on_button_up; it does
    not update is_on itself.
    """

    def __init__(self, region: Region, pens, icon_size=28):
        super().__init__(region)
        self._pens = pens
        self.is_on = False

        radius = region.height // 2
        self._bg_polygon = Polygon()
        self._bg_polygon.rectangle(*region, corners=(radius,) * 4)

        icon_x = region.x + (region.width - icon_size) // 2
        icon_y = region.y + (region.height - icon_size) // 2
        scale = icon_size / icons.MDI_POWER_VIEWBOX
        stem_x, stem_y, stem_w, stem_h = icons.MDI_POWER_STEM_RECT

        self._icon_polygon = Polygon()
        self._icon_polygon.path(
            *((icon_x + px * scale, icon_y + py * scale) for px, py in icons.MDI_POWER_OUTLINE)
        )
        self._icon_polygon.rectangle(
            icon_x + stem_x * scale, icon_y + stem_y * scale, stem_w * scale, stem_h * scale
        )

        self._vector = None

    def draw(self, display, theme):
        if self._vector is None:
            self._vector = PicoVector(display)
            self._vector.set_antialiasing(ANTIALIAS_BEST)
            self._vector.set_transform(Transform())

        bg = palette.GREEN_400 if self.is_on else palette.GRAY_900
        icon_color = palette.GREEN_900 if self.is_on else palette.GRAY_600

        display.set_pen(self._pens.get(bg))
        self._vector.draw(self._bg_polygon)
        display.set_pen(self._pens.get(icon_color))
        self._vector.draw(self._icon_polygon)


class DetailModalPage(StaticPage):
    """
    Base for tile detail modals. Draws a close button, top-right, wired to
    _close_modal (which wraps window_manager.clear_modal_page). Subclasses
    must call super().setup(region, window_manager) before appending their
    own controls, so the close button is added first.
    """

    title = ""  # a modal covers the systray anyway; no title needed

    def setup(self, region: Region, window_manager):
        p = window_manager.theme.padding
        height = window_manager.theme.control_height
        width = 100
        close_region = Region(
            region.x + region.width - p - width, region.y + p, width, height
        )
        close_button = MomentaryButton(close_region, "Close")
        close_button.on_button_up = lambda: self._close_modal(window_manager)
        self._controls.append(close_button)

    def _close_modal(self, window_manager):
        window_manager.clear_modal_page()
        # TmOS's own show_modal_page/clear_modal_page (tmos_ui.py) don't run
        # the usual will_show()/will_hide() page-transition dance for the
        # *underlying* page here -- that only fires from __update_pages() on
        # an actual current-page change, which __update_pages() itself skips
        # entirely whenever a modal is active, and closing this modal doesn't
        # change window_manager.current_page (it was never touched). Without
        # this, DashboardPage's tiles (dashboard/tiles.py, page.py) -- which
        # skip redrawing a tile whose data hasn't changed since it was last
        # drawn -- would resume ticking still marked clean from before the
        # modal opened, leaving the modal's leftover pixels on screen. Force
        # one full repaint of whatever page is underneath now that the modal
        # is gone.
        underlying = window_manager.current_page
        if underlying is not None:
            underlying.will_show()


class LightBrightnessModal(DetailModalPage):
    """
    On/off + brightness (0-255) detail view for a dimmable light: a
    vertical brightness slider (grid position 2,2, span 4x10) with a power
    toggle directly below it (span 4x2), and a label/percentage readout to
    the right (two empty grid columns away from the slider), vertically
    centered against the slider.

    Self-contained and independently testable: takes an `mqtt` object with
    a `publish(topic, payload)` method (dashboard.mqtt_client.DashboardMQTT
    in production, a stub/mock in tests) rather than depending on tiles.py.
    Opened via window_manager.show_modal_page(LightBrightnessModal(...))
    from DimmableLightTile.on_button_up.

    Local on/off + brightness state is optimistic only -- this modal never
    re-subscribes to MQTT state, so if a publish is rejected or another
    client changes the light while the modal is open, the display can
    drift from reality until the modal is closed and reopened. Pre-existing
    property of the brightness-only commit handling this class always had,
    just now extended to on/off too.
    """

    def __init__(self, domain, slug, label, mqtt, pens, initial_brightness=128, initial_state=None):
        super().__init__()
        self.domain = domain
        self.slug = slug
        self.label = label
        self._mqtt = mqtt
        self._pens = pens
        self._initial_brightness = 128 if initial_brightness is None else initial_brightness
        self._display_brightness = self._initial_brightness
        self._is_on = initial_state is True  # mirrors DimmableLightTile.draw()'s own convention
        self._slider = None
        self._power_button = None
        self._label_region = None

    def setup(self, region: Region, window_manager):
        super().setup(region, window_manager)

        slider_region = grid.cell_region(region, col=2, row=2, colspan=4, rowspan=10)
        self._slider = VerticalSliderControl(
            slider_region, 0, 255, self._initial_brightness, self._pens
        )
        self._slider.on_change = self._handle_slider_change
        self._slider.on_commit = self._handle_commit
        self._controls.append(self._slider)

        power_region = grid.cell_region(region, col=2, row=12, colspan=4, rowspan=2)
        self._power_button = PowerButton(power_region, self._pens)
        self._power_button.on_button_up = self._handle_power_toggle
        self._controls.append(self._power_button)

        # col=8 (two empty grid columns past the slider's own col=2..5)
        # per the "another cell to the right" adjustment. colspan shrinks
        # to 7 (from 8) to keep the same right-edge margin as before.
        self._label_region = grid.cell_region(region, col=8, row=2, colspan=7, rowspan=10)

    def _update(self, os):
        if self._power_button is not None:
            self._power_button.is_on = self._is_on
        if self._slider is not None:
            self._slider.is_on = self._is_on

    def _handle_slider_change(self, value):
        # Live drag feedback only -- must NOT publish MQTT here, see
        # SliderControl's own docstring on on_change.
        self._display_brightness = value
        self._is_on = True
        self.needs_update = True

    def _handle_commit(self, value):
        brightness = round(value)
        self._display_brightness = brightness
        self._is_on = True
        self._mqtt.publish(
            topics.set_topic(self.domain, self.slug),
            topics.format_light_command(True, brightness=brightness),
        )
        self.needs_update = True

    def _handle_power_toggle(self):
        self._is_on = not self._is_on
        self._mqtt.publish(
            topics.set_topic(self.domain, self.slug),
            # No brightness on the "on" payload -- lets the light resume
            # whatever level it was last at, rather than jumping to
            # _display_brightness (which may be stale from before this
            # modal was opened).
            topics.format_light_command(self._is_on),
        )
        self.needs_update = True

    def _percentage_text(self):
        # "OFF" reflects on/off state only -- a light can be on at 0%
        # brightness (e.g. mid-drag, before the user releases), which is a
        # legitimate "0%" reading, not "OFF".
        if not self._is_on:
            return "OFF"
        percent = round(self._display_brightness / 255 * 100)
        return f"{percent}%"

    def _draw(self, display, region: Region, theme):
        theme.clear_display(display, region)

        label_scale = 2
        label_w, label_h = theme.measure_text(display, self.label, rel_scale=label_scale)
        if label_w > self._label_region.width - theme.padding:
            # The label comes from the MQTT config payload and isn't
            # bounded in length -- fall back to a smaller scale rather
            # than overflowing the label region.
            label_scale = 1
            label_w, label_h = theme.measure_text(display, self.label, rel_scale=label_scale)

        value_text = self._percentage_text()
        value_scale = 4
        _, value_h = theme.measure_text(display, value_text, rel_scale=value_scale)

        gap = theme.padding
        block_height = label_h + gap + value_h
        top = self._label_region.y + (self._label_region.height - block_height) // 2

        display.set_pen(self._pens.get(palette.GRAY_300))
        theme.text(display, self.label, self._label_region.x, top, rel_scale=label_scale)

        display.set_pen(self._pens.get(palette.WHITE))
        theme.text(
            display, value_text, self._label_region.x, top + label_h + gap, rel_scale=value_scale
        )
