# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
DashboardPage(Page) -- wires config.TILES entries into grid regions, tile
instances, and state_store subscriptions.

Not a StaticPage: confirmed via real-hardware testing on the preview build
(see main.py's PreviewPage) that StaticPage's fixed execution_frequency=0
leaves SceneButtonTile's flash stuck on-screen (nothing schedules the ~400ms
redraw that fades it back out) and DateTimeTile's clock frozen between
touches. Page._tick() always fully redraws whenever invoked -- the gap is
that nothing schedules that invocation on a timer by itself under
StaticPage. A modest periodic execution_frequency covers both animations;
needs_update (set from state_store callbacks) still covers instant response
to MQTT-driven changes in between ticks.
"""

from tmos_ui import Page

from dashboard import grid, palette
from dashboard.palette import PenCache
from dashboard.tiles import DateTimeTile, DimmableLightTile, SceneButtonTile, ToggleTile, ValueTile

_TILE_BUILDERS = {}


def _tile_builder(kind):
    def register(fn):
        _TILE_BUILDERS[kind] = fn
        return fn

    return register


@_tile_builder("toggle")
def _build_toggle(spec, region, pens, mqtt, window_manager):
    if spec.get("dimmable"):
        return DimmableLightTile(
            region, pens, spec["domain"], spec["slug"], spec["label"], mqtt, window_manager
        )
    return ToggleTile(region, pens, spec["domain"], spec["slug"], spec["label"], mqtt)


@_tile_builder("sensor")
def _build_sensor(spec, region, pens, mqtt, window_manager):
    thresholds = _resolve_thresholds(spec.get("thresholds"))
    return ValueTile(region, pens, spec["label"], unit=spec.get("unit", ""), thresholds=thresholds)


@_tile_builder("scene")
def _build_scene(spec, region, pens, mqtt, window_manager):
    return SceneButtonTile(region, pens, spec["domain"], spec["slug"], spec["label"], mqtt)


@_tile_builder("datetime")
def _build_datetime(spec, region, pens, mqtt, window_manager):
    return DateTimeTile(region, pens, window_manager.os)


def _resolve_thresholds(thresholds):
    """
    config.py declares thresholds as plain data --
    [(18, "SKY_SCALE"), (25, "GREEN_SCALE"), ...] -- rather than importing
    palette tuples directly, so it stays a declarative registry. Resolves
    each scale name to its actual (background, value_text, description_text)
    triple from dashboard.palette here, at tile-construction time.

    Must be a *_SCALE name (a 3-tuple), not a single color like "SKY_400" --
    ValueTile.draw() unpacks each threshold's color as
    (bg, value_color, desc_color); a single-color name would silently
    resolve via getattr() and then fail deep inside PenCache.get() trying to
    call create_pen(*single_rgb_component).
    """
    if not thresholds:
        return None
    return [(upper_bound, getattr(palette, name)) for upper_bound, name in thresholds]


class DashboardPage(Page):
    # Page.title defaults to the literal string "Page" -- shown by TmOS's
    # own systray page-selector button (see tmos_ui.py's SystrayPageButton),
    # not anything font/theme-related. DashboardApp only ever exposes this
    # one page, so the button just needs a real label.
    title = "Dashboard"

    # 10Hz, not the plan draft's 4 -- confirmed on real hardware (see
    # main.py's PreviewPage) that SceneButtonTile's 4-step/400ms fade needs
    # roughly this rate to render as a visible fade rather than one abrupt
    # jump between ticks; the user validated the animation specifically at
    # this frequency ("Yes, it fades now").
    execution_frequency = 10

    def __init__(self, tiles_config, state, mqtt):
        super().__init__()
        self._tiles_config = tiles_config
        self._state = state
        self._mqtt = mqtt
        self._plain_tiles = []
        self._unsubscribes = []

    def setup(self, region, window_manager):
        self.teardown()
        pens = PenCache(window_manager.display)

        for spec in self._tiles_config:
            builder = _TILE_BUILDERS.get(spec["type"])
            if builder is None:
                continue
            tile_region = grid.cell_region(
                region, spec["col"], spec["row"], spec.get("colspan", 1), spec.get("rowspan", 1)
            )
            tile = builder(spec, tile_region, pens, self._mqtt, window_manager)

            domain, slug = spec.get("domain"), spec.get("slug")
            if domain and slug:
                key = "{}/{}".format(domain, slug)
                current = self._state.get(key)
                if current is not None:
                    tile.set_state(current)
                self._unsubscribes.append(self._state.on_update(key, self._make_updater(tile)))

            if hasattr(tile, "process_touch_state"):
                self._controls.append(tile)
            else:
                self._plain_tiles.append(tile)

    def _make_updater(self, tile):
        def updater(value):
            tile.set_state(value)
            self.needs_update = True

        return updater

    def _draw(self, display, region, theme):
        theme.clear_display(display, region)
        for tile in self._plain_tiles:
            tile.draw(display, theme)

    def teardown(self):
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes = []
        self._plain_tiles = []
        super().teardown()
