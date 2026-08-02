"""
Tests for dashboard.settings_page: SettingsPage, SettingsApp.
"""

from unittest import mock

import pytest

from tmos import Region

from dashboard import corners, grid, settings
from dashboard.settings_page import (
    CORNER_STYLE_LABELS,
    CORNER_STYLE_ORDER,
    FONT_CHOICE_ORDER,
    FONT_LABELS,
    RADIUS_LABELS,
    SettingsApp,
    SettingsPage,
)


def _window_manager():
    wm = mock.Mock()
    wm.display = mock.Mock()
    return wm


def _saved(**overrides):
    saved = dict(settings.DEFAULTS)
    saved.update(overrides)
    return saved


class TestSettingsPageSetup:
    def test_radio_buttons_built_from_saved_settings(self):
        # font_choice uses "default" -- currently its only valid value
        # (Atkinson/Inter are gated off, see
        # dashboard.settings_page.FONT_CHOICE_ORDER's comment) -- so this
        # only confirms the font radio still builds correctly, not an
        # override, unlike corner_style/corner_radius above.
        with mock.patch(
            "dashboard.settings_page.settings.load",
            return_value=_saved(corner_style="blocky", corner_radius="small", font_choice="default"),
        ):
            page = SettingsPage(mock.Mock())
            page.setup(Region(0, 0, 480, 480), _window_manager())

        assert page._style_radio.current_index == CORNER_STYLE_ORDER.index("blocky")
        assert page._radius_radio.current_index == corners.RADIUS_CHOICES.index("small")
        assert page._font_radio.current_index == FONT_CHOICE_ORDER.index("default")

    def test_radio_button_option_labels(self):
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)):
            page = SettingsPage(mock.Mock())
            page.setup(Region(0, 0, 480, 480), _window_manager())

        assert page._style_radio.options == list(CORNER_STYLE_LABELS)
        assert page._radius_radio.options == list(RADIUS_LABELS)
        assert page._font_radio.options == list(FONT_LABELS)

    def test_setup_registers_all_three_controls(self):
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)):
            page = SettingsPage(mock.Mock())
            page.setup(Region(0, 0, 480, 480), _window_manager())

        assert len(page._controls) == 3

    def test_groups_are_evenly_spaced_vertically(self):
        # Regression check: CORNER STYLE/RADIUS/FONT previously drifted out
        # of alignment because setup() and _draw() each hardcoded row
        # numbers independently (RADIUS immediately followed CORNER
        # STYLE's radio with no gap row, while FONT had one after
        # RADIUS's). Both now derive from the same _group_rows() helper,
        # so each group's radio must sit the same pixel distance below the
        # previous one.
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)):
            page = SettingsPage(mock.Mock())
            page.setup(Region(0, 0, 480, 480), _window_manager())

        style_y = page._style_radio.region.y
        radius_y = page._radius_radio.region.y
        font_y = page._font_radio.region.y
        assert (radius_y - style_y) == (font_y - radius_y)


class TestStyleChange:
    def test_changing_style_updates_theme_live(self):
        theme = mock.Mock()
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)), \
             mock.patch("dashboard.settings_page.settings.save") as mock_save:
            page = SettingsPage(theme)
            page.setup(Region(0, 0, 480, 480), _window_manager())

            page._style_radio.set_current_index(CORNER_STYLE_ORDER.index("blocky"))

        assert theme.corner_style == "blocky"
        mock_save.assert_called_once()
        assert mock_save.call_args.args[0]["corner_style"] == "blocky"

    def test_changing_style_marks_page_as_needing_update(self):
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)), \
             mock.patch("dashboard.settings_page.settings.save"):
            page = SettingsPage(mock.Mock())
            page.setup(Region(0, 0, 480, 480), _window_manager())
            page.needs_update = False

            page._style_radio.set_current_index(CORNER_STYLE_ORDER.index("blocky"))

        assert page.needs_update is True


class TestRadiusChange:
    def test_changing_radius_updates_theme_live(self):
        theme = mock.Mock()
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)), \
             mock.patch("dashboard.settings_page.settings.save") as mock_save:
            page = SettingsPage(theme)
            page.setup(Region(0, 0, 480, 480), _window_manager())

            page._radius_radio.set_current_index(corners.RADIUS_CHOICES.index("small"))

        assert theme.corner_radius == "small"
        mock_save.assert_called_once()
        assert mock_save.call_args.args[0]["corner_radius"] == "small"

    def test_changing_radius_marks_page_as_needing_update(self):
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)), \
             mock.patch("dashboard.settings_page.settings.save"):
            page = SettingsPage(mock.Mock())
            page.setup(Region(0, 0, 480, 480), _window_manager())
            page.needs_update = False

            page._radius_radio.set_current_index(corners.RADIUS_CHOICES.index("medium"))

        assert page.needs_update is True


class TestFontChange:
    # Atkinson/Inter are temporarily gated off (see
    # dashboard.settings_page.FONT_CHOICE_ORDER's comment -- loading a
    # PicoVector .af font hung real hardware), leaving FONT_CHOICE_ORDER
    # with only "default". RadioButton.set_current_index() is a no-op when
    # called with the already-current index, so there's no longer a
    # second option to switch to and exercise _handle_font_change's
    # apply_font_choice()/save() call with. Re-enable both tests (no other
    # changes needed) once the gate is lifted.
    @pytest.mark.skip(reason="Atkinson/Inter gated off -- only one font option exists right now")
    def test_changing_font_applies_it_live_with_the_page_display(self):
        theme = mock.Mock()
        wm = _window_manager()
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)), \
             mock.patch("dashboard.settings_page.settings.save") as mock_save:
            page = SettingsPage(theme)
            page.setup(Region(0, 0, 480, 480), wm)

            page._font_radio.set_current_index(FONT_CHOICE_ORDER.index("inter"))

        theme.apply_font_choice.assert_called_once_with(wm.display, "inter")
        mock_save.assert_called_once()
        assert mock_save.call_args.args[0]["font_choice"] == "inter"

    @pytest.mark.skip(reason="Atkinson/Inter gated off -- only one font option exists right now")
    def test_changing_font_marks_page_as_needing_update(self):
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)), \
             mock.patch("dashboard.settings_page.settings.save"):
            page = SettingsPage(mock.Mock())
            page.setup(Region(0, 0, 480, 480), _window_manager())
            page.needs_update = False

            page._font_radio.set_current_index(FONT_CHOICE_ORDER.index("atkinson"))

        assert page.needs_update is True


class TestSettingsPageDraw:
    def test_draw_clears_display_and_labels_all_three_controls(self):
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)):
            page = SettingsPage(mock.Mock())
            region = Region(0, 0, 480, 480)
            page.setup(region, _window_manager())

        display = mock.Mock()
        theme = mock.Mock()
        theme.measure_text.return_value = (50, 10)

        page._draw(display, region, theme)

        theme.clear_display.assert_called_once_with(display, region)
        text_calls = [c.args[1] for c in theme.text.call_args_list]
        assert "CORNER STYLE" in text_calls
        assert "RADIUS" in text_calls
        assert "FONT" in text_calls


class TestSettingsApp:
    def test_name_is_settings(self):
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)):
            app = SettingsApp(mock.Mock())

        assert app.name == "Settings"

    def test_pages_returns_a_single_settings_page(self):
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)):
            app = SettingsApp(mock.Mock())

        pages = app.pages()
        assert len(pages) == 1
        assert isinstance(pages[0], SettingsPage)

    def test_pages_forces_needs_setup_on_every_call(self):
        # Regression check -- same reused-instance/teardown-without-reset
        # gap as dashboard.app.DashboardApp.pages() (see its own test for
        # the full explanation): without this, revisiting Settings a second
        # time would leave its RadioButtons missing.
        with mock.patch("dashboard.settings_page.settings.load", side_effect=lambda: dict(settings.DEFAULTS)):
            app = SettingsApp(mock.Mock())
        app._page.needs_setup = False  # simulate a page already torn down once

        app.pages()

        assert app._page.needs_setup is True
