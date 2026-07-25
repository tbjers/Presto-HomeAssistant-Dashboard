# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Preview build -- NOT main.py. Confirms grid layout, theme, and tile
interactivity end-to-end on real hardware without a real MQTT broker:
LoopbackMQTT stands in for dashboard.mqtt_client.DashboardMQTT, feeding a
published /set command straight back into DashboardState as if Node-RED
round-tripped it instantly, so taps visibly respond without a broker. Kept
around (rather than deleted once config.py/app.py/mqtt_client.py landed)
as a fast `mpremote run scripts/preview_main.py` sanity check that doesn't
touch flash or require real network/broker connectivity.

The real boot sequence lives in main.py, driven by config.py + secrets.py +
dashboard.app.DashboardApp.
"""

from tmos import OS, Region
from tmos_ui import WindowManager, Page
from tmos_apps import App, AppManager

from dashboard import grid, topics
from dashboard.palette import PenCache, SKY_SCALE, GREEN_SCALE, AMBER_SCALE, ROSE_SCALE
from dashboard.state_store import DashboardState
from dashboard.theme import CompressoTheme
from dashboard.tiles import DateTimeTile, DimmableLightTile, SceneButtonTile, ToggleTile, ValueTile

TEMP_THRESHOLDS = [(18, SKY_SCALE), (25, GREEN_SCALE), (28, AMBER_SCALE), (None, ROSE_SCALE)]


class LoopbackMQTT:
    """Preview-only stand-in for DashboardMQTT."""

    def __init__(self, state: DashboardState):
        self._state = state

    def publish(self, topic, payload):
        parsed = topics.parse_topic(topic)
        if not parsed:
            return
        domain, slug, kind = parsed
        if kind != topics.SET_KIND:
            return
        value = topics.parse_state_payload(domain, payload)
        if value is not None:
            self._state.set("{}/{}".format(domain, slug), value)


class PreviewPage(Page):
    # Not a StaticPage: SceneButtonTile's flash needs a redraw ~400ms after
    # being triggered to fade back out, and DateTimeTile needs one every
    # ~1s to tick forward -- neither happens on its own without a touch or
    # an explicit needs_update, since Page._tick() always fully redraws
    # whenever it's invoked, but nothing schedules that invocation on a
    # timer by itself. A modest periodic frequency covers both; needs_update
    # (still set from MQTT-driven state changes) covers instant response to
    # non-touch-triggered updates in between ticks. 10Hz gives SceneButtonTile's
    # 4-step, 400ms fade roughly one visible step per tick.
    execution_frequency = 10

    def setup(self, region: Region, window_manager):
        pens = PenCache(window_manager.display)
        state = DashboardState()
        mqtt = LoopbackMQTT(state)
        self._unsubscribes = []

        def add(tile, domain=None, slug=None):
            if domain and slug:
                self._unsubscribes.append(
                    state.on_update("{}/{}".format(domain, slug), self._make_updater(tile))
                )
            if hasattr(tile, "process_touch_state"):
                self._controls.append(tile)
            else:
                self._plain_tiles.append(tile)

        self._plain_tiles = []

        add(
            ToggleTile(
                grid.cell_region(region, 0, 0, grid.STANDARD_SPAN, grid.STANDARD_SPAN),
                pens, "light", "lamp", "LAMP", mqtt, initial_state=True,
            ),
            "light", "lamp",
        )
        add(
            DimmableLightTile(
                grid.cell_region(region, grid.STANDARD_SPAN, 0, grid.STANDARD_SPAN, grid.STANDARD_SPAN),
                pens, "light", "ceiling", "CEILING", mqtt, window_manager,
                initial_state=True, initial_brightness=180,
            ),
            "light", "ceiling",
        )
        add(
            ValueTile(
                grid.cell_region(region, 2 * grid.STANDARD_SPAN, 0, grid.STANDARD_SPAN, grid.STANDARD_SPAN),
                pens, "OFFICE", unit="C", thresholds=TEMP_THRESHOLDS, initial_value=21,
            ),
            "sensor", "office_temp",
        )
        add(
            SceneButtonTile(
                grid.cell_region(region, 3 * grid.STANDARD_SPAN, 0, grid.STANDARD_SPAN, grid.STANDARD_SPAN),
                pens, "scene", "good_night", "GOOD NIGHT", mqtt,
            )
        )
        add(
            DateTimeTile(
                grid.cell_region(region, 0, grid.STANDARD_SPAN, 2 * grid.STANDARD_SPAN, grid.STANDARD_SPAN),
                pens, window_manager.os,
            )
        )

    def _make_updater(self, tile):
        def updater(value):
            tile.set_state(value)
            self.needs_update = True

        return updater

    def _draw(self, display, region: Region, theme):
        theme.clear_display(display, region)
        for tile in self._plain_tiles:
            tile.draw(display, theme)

    def teardown(self):
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        super().teardown()


class PreviewApp(App):
    name = "Preview"

    def pages(self):
        return [PreviewPage()]


os = OS(layers=1, full_res=True)
wm = WindowManager(os, theme=CompressoTheme())
apps = AppManager(wm)
apps.add_app(PreviewApp(), make_current=True)

os.boot(wifi=False, use_ntp=False, run=True)
