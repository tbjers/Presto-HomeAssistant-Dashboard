# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
DashboardPage(Page) -- wires one screen's tile entries into grid regions, tile
instances, and state_store subscriptions.

Not a StaticPage: confirmed via real-hardware testing on the preview build
(see main.py's PreviewPage) that StaticPage's fixed execution_frequency=0
leaves SceneButtonTile's flash stuck on-screen (nothing schedules the ~400ms
redraw that fades it back out) and DateTimeTile's clock frozen between
touches. A modest periodic execution_frequency (see DashboardPage below)
covers both animations; needs_update (set from state_store callbacks) still
covers instant response to MQTT-driven changes in between ticks.

_draw() itself does NOT unconditionally redraw every plain tile on every one
of those ticks -- each Tile tracks its own is_dirty()/mark_clean() state
(dashboard/tiles.py), so a tile whose backing value hasn't changed since it
was last drawn is skipped. This matters for WeatherTile specifically: its
icon is vector (dashboard/weather_icon.py), and re-running PicoVector curve
rendering 10x/second forever (this page's execution_frequency) for an icon
that changes on the order of minutes would be real, avoidable waste --
dirty-tracking is what makes vector viable there. Control-based tiles
(ToggleTile, SceneButtonTile, DimmableLightTile) are unaffected by this --
they're drawn by TmOS's own vendored Page._tick() loop over self._controls,
not by _draw(), so dirty-tracking doesn't (and can't, without hand-editing
vendored code) apply to them.

Because individual tiles can now skip their own redraw, _draw() also stops
unconditionally clearing the whole page's region on every tick -- see
will_show() and the _needs_full_clear flag -- since blanking the region
every tick would erase already-correct pixels for tiles that were about to
be skipped as "clean".
"""

from tmos_ui import Page

from dashboard import grid, palette
from dashboard.palette import PenCache
from dashboard.tiles import (
    DateTimeTile,
    DimmableLightTile,
    SceneButtonTile,
    ToggleTile,
    ValueTile,
    WeatherTile,
)

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


@_tile_builder("weather")
def _build_weather(spec, region, pens, mqtt, window_manager):
    return WeatherTile(region, pens, spec["label"], unit=spec.get("unit", ""))


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
    # 10Hz, not the plan draft's 4 -- confirmed on real hardware (see
    # main.py's PreviewPage) that SceneButtonTile's 4-step/400ms fade needs
    # roughly this rate to render as a visible fade rather than one abrupt
    # jump between ticks; the user validated the animation specifically at
    # this frequency ("Yes, it fades now").
    execution_frequency = 10

    def __init__(self, title, tiles_config, state, mqtt):
        super().__init__()
        # Page.title defaults to the literal string "Page" -- shown by
        # TmOS's own systray page-selector button (see tmos_ui.py's
        # SystrayPageButton). DashboardApp can expose more than one screen,
        # so each instance needs its own label rather than a shared class
        # attribute.
        self.title = title
        self._tiles_config = tiles_config
        self._state = state
        self._mqtt = mqtt
        self._plain_tiles = []
        self._unsubscribes = []
        self._needs_full_clear = True

    def setup(self, region, window_manager):
        self.teardown()
        self._needs_full_clear = True
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

    def will_show(self):
        # Called every time this page becomes the current one again (not
        # just on first display) -- whatever page was shown in between may
        # have overwritten this page's pixels, so force one full repaint
        # regardless of which tiles' own data actually changed. Without
        # this, a plain tile whose value hasn't changed since it was last
        # drawn would stay skipped by is_dirty() and never repaint the
        # stale content left behind by the other page.
        self._needs_full_clear = True
        for tile in self._plain_tiles:
            tile.mark_dirty()

    def _draw(self, display, region, theme):
        if self._needs_full_clear:
            theme.clear_display(display, region)
            self._needs_full_clear = False
        for tile in self._plain_tiles:
            if not tile.is_dirty():
                continue
            tile.draw(display, theme)
            tile.mark_clean()

    def teardown(self):
        for unsubscribe in self._unsubscribes:
            unsubscribe()
        self._unsubscribes = []
        self._plain_tiles = []
        super().teardown()
