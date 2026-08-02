# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
SettingsApp(App) -- a device-local settings screen, reached the same way
DashboardApp itself is: via the existing hamburger/AppSwitcher systray
accessory (tmos_apps.py's AppManager), not a modal or a second systray
icon. Registering it as a second App means "SETTINGS" simply appears as a
second row alongside "DASHBOARD" in the app switcher list that's already
there -- no new UI chrome needed.

Unlike dashboard.modal's tile-detail modals (which overlay the current
dashboard page for a quick, contextual tweak), this is a full navigational
destination: selecting it swaps out the dashboard entirely (AppManager's
set_current_app), the same way switching to any other app would. The user
returns to the dashboard the same way they got here -- hamburger menu,
DASHBOARD.

RadioButton (tmos_ui.py) is reused for all three controls rather than a
custom slider/button row -- every setting here is a small, fixed set of
discrete choices, exactly what RadioButton is for. CORNER STYLE (smooth vs
blocky) and RADIUS (square/small/medium/large) are deliberately separate,
orthogonal controls -- see dashboard/corners.py and dashboard/theme.py's
module docstrings for how they combine into an actual pixel radius.
"""

from tmos_ui import RadioButton, StaticPage
from tmos_apps import App

from dashboard import corners, grid, settings

# 1:1 with dashboard.theme.CompressoTheme.CORNER_STYLE_CHOICES, in display
# order.
CORNER_STYLE_ORDER = ("smooth", "blocky")
CORNER_STYLE_LABELS = ("SMOOTH", "BLOCKY")

# 1:1 with dashboard.corners.RADIUS_CHOICES, in display order.
RADIUS_LABELS = ("SQUARE", "SMALL", "MEDIUM", "LARGE")

# 1:1 with dashboard.theme.CompressoTheme.FONT_CHOICES' keys, in a fixed
# display order (dicts are unordered enough not to rely on for indexing).
#
# Atkinson/Inter are temporarily gated off here -- selecting either loads
# a PicoVector .af font, which hung real hardware hard enough to require
# a physical power-cycle to recover (confirmed on-device: the hang
# reproduces with WindowManager(theme=...) construction alone, so it's
# not specific to any one code path or the base_font_scale-ordering bug
# that was also fixed in dashboard.theme.CompressoTheme.setup() -- that
# fix is necessary but wasn't sufficient). Re-enable by restoring the
# commented-out entries here and in dashboard.theme.CompressoTheme.
# FONT_CHOICES / dashboard.settings.VALID_FONT_CHOICES once the
# underlying PicoVector .af loading issue is root-caused -- the asset
# files and apply_font_choice()/_configure_font_metrics() are untouched.
FONT_CHOICE_ORDER = ("default",)  # "atkinson", "inter"
FONT_LABELS = ("DEFAULT",)  # "ATKINSON", "INTER"

# Every settings group (label + RadioButton) occupies the same number of
# grid rows, so groups stay evenly spaced regardless of how many are added
# -- label row, radio rows, then a blank gap row before the next group's
# label. setup() and _draw() both derive their row numbers from
# _group_rows() rather than hardcoding them independently, which is what
# let CORNER STYLE/RADIUS/FONT drift out of alignment with each other in
# the first place (RADIUS immediately followed CORNER STYLE's radio with
# no gap row, while FONT had one after RADIUS's).
_LABEL_ROWSPAN = 1
_RADIO_ROWSPAN = 2
_GROUP_GAP_ROWS = 1
_GROUP_HEIGHT = _LABEL_ROWSPAN + _RADIO_ROWSPAN + _GROUP_GAP_ROWS
_FIRST_GROUP_ROW = 1


def _group_rows(index):
    """Returns (label_row, radio_row) for the index-th (0-based) settings
    group -- see _GROUP_HEIGHT above."""
    label_row = _FIRST_GROUP_ROW + index * _GROUP_HEIGHT
    return label_row, label_row + _LABEL_ROWSPAN


class SettingsPage(StaticPage):
    title = "Settings"

    def __init__(self, theme):
        super().__init__()
        self._theme = theme
        self._display = None
        self._settings = settings.load()
        self._style_radio = None
        self._radius_radio = None
        self._font_radio = None

    def setup(self, region, window_manager):
        self._display = window_manager.display
        self._controls = []

        _, style_radio_row = _group_rows(0)
        style_region = grid.cell_region(
            region, col=1, row=style_radio_row, colspan=14, rowspan=_RADIO_ROWSPAN
        )
        self._style_radio = RadioButton(
            style_region,
            list(CORNER_STYLE_LABELS),
            current_index=CORNER_STYLE_ORDER.index(self._settings["corner_style"]),
        )
        self._style_radio.on_current_index_changed = self._handle_style_change
        self._controls.append(self._style_radio)

        _, radius_radio_row = _group_rows(1)
        radius_region = grid.cell_region(
            region, col=1, row=radius_radio_row, colspan=14, rowspan=_RADIO_ROWSPAN
        )
        self._radius_radio = RadioButton(
            radius_region,
            list(RADIUS_LABELS),
            current_index=corners.RADIUS_CHOICES.index(self._settings["corner_radius"]),
        )
        self._radius_radio.on_current_index_changed = self._handle_radius_change
        self._controls.append(self._radius_radio)

        _, font_radio_row = _group_rows(2)
        font_region = grid.cell_region(
            region, col=1, row=font_radio_row, colspan=14, rowspan=_RADIO_ROWSPAN
        )
        self._font_radio = RadioButton(
            font_region,
            list(FONT_LABELS),
            current_index=FONT_CHOICE_ORDER.index(self._settings["font_choice"]),
        )
        self._font_radio.on_current_index_changed = self._handle_font_change
        self._controls.append(self._font_radio)

    def _handle_style_change(self, index):
        self._settings["corner_style"] = CORNER_STYLE_ORDER[index]
        self._theme.corner_style = self._settings["corner_style"]
        settings.save(self._settings)
        self.needs_update = True

    def _handle_radius_change(self, index):
        self._settings["corner_radius"] = corners.RADIUS_CHOICES[index]
        self._theme.corner_radius = self._settings["corner_radius"]
        settings.save(self._settings)
        self.needs_update = True

    def _handle_font_change(self, index):
        choice = FONT_CHOICE_ORDER[index]
        self._settings["font_choice"] = choice
        self._theme.apply_font_choice(self._display, choice)
        settings.save(self._settings)
        self.needs_update = True
        # Known gap: this repaints SettingsPage's own content (needs_update
        # above), but not the systray (tab labels/clock) -- WindowManager
        # (tmos_ui.py) exposes no public "force a systray repaint" hook,
        # only ones tied to actually adding/removing an accessory. The
        # systray naturally repaints in the new font next time its own
        # page/tab set changes (e.g. navigating back to Dashboard), so this
        # is stale only for as long as the user stays on this page.

    def _draw(self, display, region, theme):
        theme.clear_display(display, region)

        label_scale = 1
        style_label_row, _ = _group_rows(0)
        radius_label_row, _ = _group_rows(1)
        font_label_row, _ = _group_rows(2)
        style_label_y = grid.cell_region(
            region, col=1, row=style_label_row, colspan=14, rowspan=_LABEL_ROWSPAN
        ).y
        radius_label_y = grid.cell_region(
            region, col=1, row=radius_label_row, colspan=14, rowspan=_LABEL_ROWSPAN
        ).y
        font_label_y = grid.cell_region(
            region, col=1, row=font_label_row, colspan=14, rowspan=_LABEL_ROWSPAN
        ).y
        x = self._style_radio.region.x

        display.set_pen(theme.foreground_pen)
        theme.text(display, "CORNER STYLE", x, style_label_y, rel_scale=label_scale)
        theme.text(display, "RADIUS", x, radius_label_y, rel_scale=label_scale)
        theme.text(display, "FONT", x, font_label_y, rel_scale=label_scale)


class SettingsApp(App):
    name = "Settings"

    def __init__(self, theme):
        self._theme = theme
        self._page = SettingsPage(theme)

    def pages(self):
        # Force a fresh setup() every time this app becomes current again --
        # see dashboard/app.py's DashboardApp.pages() for the full
        # explanation (the same reused-instance/teardown-without-reset gap
        # applies here too: SettingsPage's RadioButtons would go missing on
        # the second visit without this).
        self._page.needs_setup = True
        return [self._page]
