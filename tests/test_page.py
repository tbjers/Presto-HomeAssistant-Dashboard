"""
Tests for dashboard.page.DashboardPage.
"""

from unittest import mock

from tmos import Region

from dashboard import topics
from dashboard.page import DashboardPage
from dashboard.state_store import DashboardState


def _touch(factory, state, x=0, y=0):
    t = factory()
    t.state = state
    t.x = x
    t.y = y
    return t


def _window_manager():
    wm = mock.Mock()
    wm.theme.padding = 8
    wm.theme.control_height = 53
    wm.os.localtime.return_value = (2026, 7, 24, 9, 5, 0, 4, 205)
    return wm


TILES = [
    {"type": "toggle", "domain": "light", "slug": "lamp", "label": "LAMP", "col": 0, "row": 0},
    {
        "type": "toggle", "domain": "light", "slug": "ceiling", "label": "CEILING", "dimmable": True,
        "col": 4, "row": 0,
    },
    {
        "type": "sensor", "domain": "sensor", "slug": "office_temp", "label": "OFFICE", "unit": "C",
        "col": 8, "row": 0,
        "thresholds": [(18, "SKY_SCALE"), (25, "GREEN_SCALE"), (28, "AMBER_SCALE"), (None, "ROSE_SCALE")],
    },
    {"type": "scene", "domain": "scene", "slug": "good_night", "label": "GOOD NIGHT", "col": 12, "row": 0},
    {"type": "datetime", "col": 0, "row": 4, "colspan": 8},
]


class TestDashboardPageTitle:
    def test_title_comes_from_constructor(self):
        page = DashboardPage("Bedroom", TILES, DashboardState(), mock.Mock())

        assert page.title == "Bedroom"


class TestDashboardPageSetup:
    def test_setup_partitions_controls_and_plain_tiles(self):
        page = DashboardPage("Dashboard", TILES, DashboardState(), mock.Mock())
        page.setup(Region(0, 0, 480, 480), _window_manager())

        # toggle x2 + scene = 3 Control tiles; sensor + datetime = 2 plain tiles.
        assert len(page._controls) == 3
        assert len(page._plain_tiles) == 2

    def test_setup_seeds_tiles_from_existing_state(self):
        state = DashboardState()
        state.set("light/lamp", {"state": "on"})
        page = DashboardPage("Dashboard", TILES, state, mock.Mock())
        page.setup(Region(0, 0, 480, 480), _window_manager())

        lamp_tile = page._controls[0]
        assert lamp_tile._state is True

    def test_state_update_after_setup_updates_tile_and_needs_update(self):
        state = DashboardState()
        page = DashboardPage("Dashboard", TILES, state, mock.Mock())
        page.setup(Region(0, 0, 480, 480), _window_manager())
        page.needs_update = False

        state.set("light/lamp", {"state": "on"})

        lamp_tile = page._controls[0]
        assert lamp_tile._state is True
        assert page.needs_update is True

    def test_resolves_string_threshold_names_to_palette_scales(self):
        from dashboard import palette

        page = DashboardPage("Dashboard", TILES, DashboardState(), mock.Mock())
        page.setup(Region(0, 0, 480, 480), _window_manager())

        sensor_tile = page._plain_tiles[0]
        assert sensor_tile.thresholds[0] == (18, palette.SKY_SCALE)

    def test_re_setup_unsubscribes_previous_listeners(self):
        state = DashboardState()
        page = DashboardPage("Dashboard", TILES, state, mock.Mock())
        page.setup(Region(0, 0, 480, 480), _window_manager())
        first_lamp_tile = page._controls[0]

        page.setup(Region(0, 0, 480, 480), _window_manager())

        state.set("light/lamp", {"state": "on"})
        assert first_lamp_tile._state is None  # stale tile no longer subscribed


class TestDashboardPageTouch:
    def test_tap_on_toggle_tile_publishes_via_mqtt(self, mock_touch_factory):
        mqtt = mock.Mock()
        page = DashboardPage("Dashboard", TILES, DashboardState(), mqtt)
        page.setup(Region(0, 0, 480, 480), _window_manager())

        lamp_tile = page._controls[0]
        region = lamp_tile.region
        lamp_tile.process_touch_state(_touch(mock_touch_factory, True, region.x + 5, region.y + 5))
        lamp_tile.process_touch_state(_touch(mock_touch_factory, False, region.x + 5, region.y + 5))

        mqtt.publish.assert_called_once_with(
            topics.set_topic("light", "lamp"), topics.format_light_command(True)
        )

    def test_tap_on_dimmable_light_opens_modal(self, mock_touch_factory):
        window_manager = _window_manager()
        page = DashboardPage("Dashboard", TILES, DashboardState(), mock.Mock())
        page.setup(Region(0, 0, 480, 480), window_manager)

        ceiling_tile = page._controls[1]
        region = ceiling_tile.region
        ceiling_tile.process_touch_state(_touch(mock_touch_factory, True, region.x + 5, region.y + 5))
        ceiling_tile.process_touch_state(_touch(mock_touch_factory, False, region.x + 5, region.y + 5))

        window_manager.show_modal_page.assert_called_once()


class TestDashboardPageDrawAndTeardown:
    def test_draw_clears_display_and_draws_plain_tiles_only(self):
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        page = DashboardPage("Dashboard", TILES, DashboardState(), mock.Mock())
        page.setup(Region(0, 0, 480, 480), _window_manager())

        page._draw(display, Region(0, 0, 480, 480), theme)

        theme.clear_display.assert_called_once()

    def test_teardown_unsubscribes_all_listeners(self):
        state = DashboardState()
        page = DashboardPage("Dashboard", TILES, state, mock.Mock())
        page.setup(Region(0, 0, 480, 480), _window_manager())
        lamp_tile = page._controls[0]

        page.teardown()

        state.set("light/lamp", {"state": "on"})
        assert lamp_tile._state is None


class TestDashboardPageDirtyTracking:
    def _draw_page(self, page, display, theme):
        page._draw(display, Region(0, 0, 480, 480), theme)

    def test_second_draw_without_changes_skips_already_clean_tiles(self):
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        page = DashboardPage("Dashboard", TILES, DashboardState(), mock.Mock())
        page.setup(Region(0, 0, 480, 480), _window_manager())

        self._draw_page(page, display, theme)
        first_text_calls = theme.text.call_count

        self._draw_page(page, display, theme)

        assert theme.text.call_count == first_text_calls  # nothing redrawn
        assert theme.clear_display.call_count == 1  # only cleared once

    def test_state_change_redraws_only_the_changed_tile(self):
        state = DashboardState()
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        page = DashboardPage("Dashboard", TILES, state, mock.Mock())
        page.setup(Region(0, 0, 480, 480), _window_manager())
        self._draw_page(page, display, theme)
        theme.text.reset_mock()

        state.set("sensor/office_temp", {"value": 23})
        self._draw_page(page, display, theme)

        rendered = [c.args[1] for c in theme.text.call_args_list]
        assert "23" in rendered
        # DateTimeTile's clock value hasn't changed (same mocked minute), so
        # it should have stayed clean and not redrawn.
        assert "Friday, 24.07." not in rendered

    def test_will_show_forces_a_full_clear_and_redraw(self):
        display = mock.Mock()
        theme = mock.Mock(padding=8)
        theme.measure_text.return_value = (20, 10)
        page = DashboardPage("Dashboard", TILES, DashboardState(), mock.Mock())
        page.setup(Region(0, 0, 480, 480), _window_manager())
        self._draw_page(page, display, theme)
        theme.clear_display.reset_mock()
        theme.text.reset_mock()

        page.will_show()
        self._draw_page(page, display, theme)

        theme.clear_display.assert_called_once()
        assert theme.text.call_count > 0
