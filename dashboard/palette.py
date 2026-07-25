"""
Color palette, ported verbatim (same rgb values) from compresto's ui.py, plus
a PenCache for turning these plain (r, g, b) tuples into real PicoGraphics
pen handles at runtime, and a generic threshold-to-color helper.
"""

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

GRAY_950 = (10, 10, 10)
GRAY_900 = (23, 23, 23)
GRAY_800 = (38, 38, 38)
GRAY_700 = (64, 64, 64)
GRAY_600 = (82, 82, 82)
GRAY_500 = (115, 115, 115)
GRAY_400 = (163, 163, 163)
GRAY_300 = (212, 212, 212)
GRAY_200 = (229, 229, 229)
GRAY_100 = (245, 245, 245)
GRAY_50 = (250, 250, 250)

GREEN_400 = (74, 222, 128)
GREEN_500 = (34, 197, 94)
GREEN_600 = (22, 163, 74)
GREEN_800 = (22, 101, 52)
GREEN_900 = (20, 83, 45)

ROSE_400 = (248, 113, 113)
ROSE_600 = (225, 29, 72)
ROSE_800 = (159, 18, 57)
ROSE_900 = (127, 29, 29)

SKY_400 = (56, 189, 248)
SKY_600 = (2, 132, 199)
SKY_800 = (7, 89, 133)
SKY_900 = (12, 74, 110)

PURPLE_600 = (147, 51, 234)

AMBER_400 = (251, 191, 36)
AMBER_500 = (234, 179, 8)
AMBER_600 = (217, 119, 6)
AMBER_800 = (146, 64, 14)
AMBER_900 = (120, 53, 15)

# "Scale" triples: (background, value_text, description_text), ported
# directly from compresto's TemperatureTile/ValueTile pattern -- a bright,
# saturated background needs a dark color of the same family for text to
# stay legible on top of it, not a flat neutral like GRAY_200. NEUTRAL_SCALE
# is compresto's ValueTile default (no threshold match / value is None).
NEUTRAL_SCALE = (GRAY_900, GRAY_200, GRAY_600)
SKY_SCALE = (SKY_400, SKY_900, SKY_600)
GREEN_SCALE = (GREEN_400, GREEN_900, GREEN_600)
AMBER_SCALE = (AMBER_400, AMBER_900, AMBER_600)
ROSE_SCALE = (ROSE_400, ROSE_900, ROSE_600)


class PenCache:
    """Lazily creates and caches display.create_pen(*rgb) results, keyed by
    rgb tuple, since pens are runtime handles rather than constants."""

    def __init__(self, display):
        self._display = display
        self._pens = {}

    def get(self, rgb: tuple) -> int:
        pen = self._pens.get(rgb)
        if pen is None:
            pen = self._display.create_pen(*rgb)
            self._pens[rgb] = pen
        return pen


def color_for_thresholds(value, thresholds, default=None):
    """
    Picks a color for `value` from an ordered `thresholds` list of
    `(upper_bound, color)` pairs, e.g. mirroring compresto's TemperatureTile:
        [(18, SKY_400), (25, GREEN_400), (28, AMBER_400), (None, ROSE_400)]
    Returns the color for the first entry whose upper_bound is None or
    value < upper_bound. Returns `default` if value is None or thresholds
    is empty.
    """
    if value is None or not thresholds:
        return default
    for upper_bound, color in thresholds:
        if upper_bound is None or value < upper_bound:
            return color
    return thresholds[-1][1]
