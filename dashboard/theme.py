"""
CompressoTheme(DefaultTheme) — a TmOS Theme subclass giving the systray and
any other native TmOS chrome a look consistent with the tile grid, instead
of DefaultTheme's white background clashing with a black dashboard. Tiles
themselves are drawn directly from dashboard.palette (which has far more
colors than Theme's 4 semantic pens) — this theme only governs TmOS's own
native rendering (systray, page/app-switcher buttons).

Assumes the app always boots with full_res=True (see main.py), so
display.get_bounds() is always (480, 480) and dpi_scale_factor is always 2.
dashboard.grid's GAP/COLUMNS constants are tuned specifically for that
480px-wide regime and would be unusably cramped at the 240px reference
resolution TmOS itself uses for Theme's automatic dpi-scaling (padding and
systray_height are in Theme._dpi_scaled_sizes and get multiplied by
dpi_scale_factor during setup() — rather than working out what reference
value scales up to our desired final pixel value, we just set them directly
after calling the base setup()).
"""

from tmos_ui import DefaultTheme

from dashboard import grid, palette


class CompressoTheme(DefaultTheme):
    background_pen = palette.GRAY_950
    foreground_pen = palette.GRAY_200
    secondary_background_pen = palette.GRAY_900
    error_pen = palette.ROSE_600

    # font: DefaultTheme's "bitmap8" is a reasonable v1 fallback; compresto's
    # chunky bold numerals suggest a custom vector (.af) font would get
    # closer to the reference look. Deferred, not a v1 blocker.

    def setup(self, display, dpi_scale_factor):
        super().setup(display, dpi_scale_factor)
        self.padding = grid.GAP
        self.systray_height = round(grid.span_size(grid.tile_size(480), 2))
