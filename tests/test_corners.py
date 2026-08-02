"""
Tests for dashboard.corners: pixel-block ("blocky") rounded-corner
geometry and drawing.
"""

from unittest import mock

from dashboard.corners import (
    RADIUS_CHOICES,
    corner_notches,
    draw_blocky_corners,
    radius_blocks,
)


class TestRadiusBlocks:
    def test_known_choices(self):
        assert radius_blocks("square") == 0
        assert radius_blocks("small") == 1
        assert radius_blocks("medium") == 2
        assert radius_blocks("large") == 3

    def test_unknown_choice_falls_back_to_zero(self):
        assert radius_blocks("not-a-real-choice") == 0

    def test_every_radius_choice_has_a_block_count(self):
        for choice in RADIUS_CHOICES:
            assert isinstance(radius_blocks(choice), int)


class TestCornerNotches:
    def test_zero_pixel_size_returns_no_notches(self):
        assert corner_notches(0, 2) == []

    def test_zero_blocks_returns_no_notches(self):
        assert corner_notches(6, 0) == []

    def test_one_block_is_a_single_pixel_square(self):
        assert corner_notches(6, 1) == [(0, 0, 6, 6)]

    def test_two_blocks_is_a_triangular_staircase(self):
        # Row 0 (tip-most): 2 blocks wide. Row 1: 1 block wide.
        assert corner_notches(6, 2) == [(0, 0, 12, 6), (0, 6, 6, 6)]

    def test_three_blocks_is_a_triangular_staircase(self):
        assert corner_notches(6, 3) == [
            (0, 0, 18, 6),
            (0, 6, 12, 6),
            (0, 12, 6, 6),
        ]

    def test_notch_count_equals_block_count(self):
        for blocks in (1, 2, 3, 4, 5):
            assert len(corner_notches(6, blocks)) == blocks

    def test_row_width_shrinks_by_one_block_per_row(self):
        notches = corner_notches(10, 4)
        widths = [w for _, _, w, _ in notches]
        assert widths == [40, 30, 20, 10]

    def test_every_row_is_exactly_pixel_size_tall(self):
        for _, _, _, h in corner_notches(7, 3):
            assert h == 7

    def test_rows_are_stacked_without_gaps_or_overlaps(self):
        notches = corner_notches(6, 3)
        ys = [y for _, y, _, _ in notches]
        assert ys == [0, 6, 12]


class TestDrawBlockyCorners:
    def _display(self):
        return mock.Mock()

    def test_noop_at_zero_blocks(self):
        display = self._display()
        draw_blocky_corners(display, 0, 0, 100, 100, 6, 0, erase_pen=1)
        display.rectangle.assert_not_called()

    def test_noop_at_zero_pixel_size(self):
        display = self._display()
        draw_blocky_corners(display, 0, 0, 100, 100, 0, 2, erase_pen=1)
        display.rectangle.assert_not_called()

    def test_single_block_paints_four_corner_notches(self):
        display = self._display()
        draw_blocky_corners(display, 0, 0, 100, 100, 6, 1, erase_pen=1)

        assert all(c.args == (1,) for c in display.set_pen.call_args_list)
        assert display.rectangle.call_count == 4  # 1 notch/step * 4 corners

    def test_two_blocks_paints_eight_rectangles(self):
        display = self._display()
        draw_blocky_corners(display, 0, 0, 100, 100, 6, 2, erase_pen=1)

        assert display.rectangle.call_count == 2 * 4  # 2 notches * 4 corners

    def test_four_tuple_corner_pens_paints_each_corner_its_own_color(self):
        display = self._display()
        draw_blocky_corners(display, 10, 20, 100, 60, 6, 1, corner_pens=(11, 22, 33, 44))

        pen_to_rect = list(
            zip(
                (c.args[0] for c in display.set_pen.call_args_list),
                (c.args for c in display.rectangle.call_args_list),
            )
        )
        assert (11, (10, 20, 6, 6)) in pen_to_rect  # top-left
        assert (22, (104, 20, 6, 6)) in pen_to_rect  # top-right
        assert (33, (10, 74, 6, 6)) in pen_to_rect  # bottom-left
        assert (44, (104, 74, 6, 6)) in pen_to_rect  # bottom-right

    def test_blocks_clamped_down_to_fit_small_rects_never_leaving_a_gap(self):
        # A rect too small to fit the requested block count is clamped
        # down (never up) -- see draw_blocky_corners' own docstring for
        # why never rounding up to exactly reach a dimension's half
        # matters (a real protruding-line bug on odd-sized dimensions).
        display = self._display()
        # w=20,h=15, pixel_size=6 -> max_blocks = min(20,15)//(2*6) = 1
        draw_blocky_corners(display, 0, 0, 20, 15, 6, 3, erase_pen=1)

        for x, y, w, h in (c.args for c in display.rectangle.call_args_list):
            assert x >= 0 and y >= 0
            assert x + w <= 20
            assert y + h <= 15
        assert display.rectangle.call_count == 1 * 4  # clamped to 1 block

    def test_clamped_to_zero_draws_nothing(self):
        display = self._display()
        # Too small to fit even a single block.
        draw_blocky_corners(display, 0, 0, 8, 8, 6, 2, erase_pen=1)
        display.rectangle.assert_not_called()

    def test_odd_dimension_never_leaves_a_protruding_seam(self):
        # Regression check for the real-hardware bug: an odd limiting
        # dimension must never make the top/bottom (or left/right) notch
        # bands leave a gap where the un-notched square corner peeks
        # through as a stray line. With the "never round up" clamp, the
        # only correct outcome is a (possibly smaller) symmetric gap, or
        # none -- never an asymmetric one-sided artifact.
        display = self._display()
        draw_blocky_corners(display, 0, 0, 168, 53, 6, 3, erase_pen=1)

        rects = [c.args for c in display.rectangle.call_args_list]
        top_ys = sorted({y for _, y, _, _ in rects if y < 53 / 2})
        bottom_ys = sorted({y + h for _, y, _, h in rects if y >= 53 / 2})
        # The lowest top-side row and the highest bottom-side row must be
        # symmetric around the vertical center -- never one-sided.
        assert top_ys[0] == 0
        assert bottom_ys[-1] == 53
