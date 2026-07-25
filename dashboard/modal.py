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

from tmos import Region
from tmos_ui import Control, MomentaryButton, StaticPage, is_within

from dashboard import palette, topics


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
                self._update_value(touch.x)
            return

        if touch_active:
            self._update_value(touch.x)
        else:
            self._is_dragging = False
            self._event("on_commit", self.value)

    def _update_value(self, touch_x):
        fraction = _clamp((touch_x - self.region.x) / self.region.width, 0.0, 1.0)
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


class DetailModalPage(StaticPage):
    """
    Base for tile detail modals. Draws a close button, top-right, wired to
    window_manager.clear_modal_page. Subclasses must call
    super().setup(region, window_manager) before appending their own
    controls, so the close button is added first.
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
        close_button.on_button_up = window_manager.clear_modal_page
        self._controls.append(close_button)


class LightBrightnessModal(DetailModalPage):
    """
    On/off + brightness (0-255) detail view for a dimmable light.

    Self-contained and independently testable: takes an `mqtt` object with
    a `publish(topic, payload)` method (dashboard.mqtt_client.DashboardMQTT
    in production, a stub/mock in tests) rather than depending on tiles.py.
    Opened via window_manager.show_modal_page(LightBrightnessModal(...))
    from DimmableLightTile.on_button_up.
    """

    def __init__(self, domain, slug, label, mqtt, pens, initial_brightness=128):
        super().__init__()
        self.domain = domain
        self.slug = slug
        self.label = label
        self._mqtt = mqtt
        self._pens = pens
        self._initial_brightness = 128 if initial_brightness is None else initial_brightness
        self._slider = None

    def setup(self, region: Region, window_manager):
        super().setup(region, window_manager)
        p = window_manager.theme.padding
        slider_region = Region(
            region.x + p, region.y + region.height // 2, region.width - 2 * p, 40
        )
        self._slider = SliderControl(slider_region, 0, 255, self._initial_brightness, self._pens)
        self._slider.on_commit = self._handle_commit
        self._controls.append(self._slider)

    def _handle_commit(self, value):
        brightness = round(value)
        self._mqtt.publish(
            topics.set_topic(self.domain, self.slug),
            topics.format_light_command(True, brightness=brightness),
        )
        self.needs_update = True

    def _draw(self, display, region: Region, theme):
        theme.clear_display(display, region)
        theme.text(display, self.label, region.x + theme.padding, region.y + theme.padding, rel_scale=2)
