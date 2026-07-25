"""
Tests for dashboard.icons -- just data-shape sanity checks. The actual
point values are generated data (see scripts/flatten_icon.py); verifying
them against the source SVG is a visual check, not a unit test concern.
"""

from dashboard.icons import HOME_ASSISTANT_DOTS, HOME_ASSISTANT_OUTLINE, HOME_ASSISTANT_VIEWBOX


class TestHomeAssistantIcon:
    def test_outline_is_points_within_the_viewbox(self):
        assert len(HOME_ASSISTANT_OUTLINE) > 2
        for x, y in HOME_ASSISTANT_OUTLINE:
            assert 0 <= x <= HOME_ASSISTANT_VIEWBOX
            assert 0 <= y <= HOME_ASSISTANT_VIEWBOX

    def test_dots_are_center_radius_triples_within_the_viewbox(self):
        assert len(HOME_ASSISTANT_DOTS) == 3
        for cx, cy, r in HOME_ASSISTANT_DOTS:
            assert 0 < r < HOME_ASSISTANT_VIEWBOX
            assert 0 <= cx <= HOME_ASSISTANT_VIEWBOX
            assert 0 <= cy <= HOME_ASSISTANT_VIEWBOX
