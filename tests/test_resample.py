"""
Tests for dashboard.resample. Host-side this exercises the pure-Python
resample() fallback; the viper twin (dashboard/_resample_viper.py) is
checked against it on-device by scripts/camera_smoke_test.py.
"""

import array

import pytest

from dashboard.resample import decode_shift, fit_rect, parse_aspect, resample


class TestParseAspect:
    @pytest.mark.parametrize(
        "value, expected",
        [("16:9", 16 / 9), ("4:3", 4 / 3), (1.5, 1.5), ("1.5", 1.5)],
    )
    def test_valid(self, value, expected):
        assert parse_aspect(value) == pytest.approx(expected)

    @pytest.mark.parametrize("value", [None, "wide", "16:0", "0:9", -1, "a:b"])
    def test_unusable_means_none(self, value):
        assert parse_aspect(value) is None


class TestFitRect:
    AREA = (0, 78, 480, 402)

    def test_16_9_is_width_limited_and_vertically_centered(self):
        assert fit_rect(self.AREA, 704, 480, 16 / 9) == (0, 144, 480, 270)

    def test_default_aspect_is_frame_pixel_shape(self):
        assert fit_rect(self.AREA, 704, 480) == (0, 115, 480, 327)

    def test_tall_aspect_is_height_limited_and_horizontally_centered(self):
        x, y, w, h = fit_rect(self.AREA, 480, 640)  # 3:4 portrait
        assert (y, h) == (78, 402)
        assert w == round(402 * 3 / 4)
        assert x == (480 - w) // 2

    def test_never_exceeds_area(self):
        for aspect in (0.3, 1.0, 4 / 3, 16 / 9, 3.0):
            x, y, w, h = fit_rect(self.AREA, 704, 480, aspect)
            assert x >= 0 and y >= 78 and x + w <= 480 and y + h <= 78 + 402


class TestDecodeShift:
    def test_full_when_half_would_be_too_small(self):
        assert decode_shift(704, 480, 480, 270) == 0

    def test_half_when_it_still_covers_target(self):
        assert decode_shift(1280, 720, 480, 270) == 1

    def test_quarter_and_eighth(self):
        assert decode_shift(1920, 1080, 480, 270) == 2
        assert decode_shift(3840, 2160, 480, 270) == 3


def _image(w, h, fn):
    return array.array("H", [fn(x, y) for y in range(h) for x in range(w)])


class TestResample:
    def test_identity_copy(self):
        src = _image(4, 3, lambda x, y: y * 10 + x)
        dst = array.array("H", [0] * (4 * 3))
        resample(src, 4, 3, dst, 4, 0, 0, 4, 3)
        assert dst == src

    def test_downscale_by_two_picks_every_other_pixel(self):
        src = _image(4, 4, lambda x, y: y * 10 + x)
        dst = array.array("H", [0] * 4)
        resample(src, 4, 4, dst, 2, 0, 0, 2, 2)
        assert list(dst) == [0, 2, 20, 22]

    def test_writes_only_target_rect_at_offset(self):
        src = _image(2, 2, lambda x, y: 1 + y * 2 + x)
        dst = array.array("H", [0xFFFF] * (5 * 4))
        resample(src, 2, 2, dst, 5, 2, 1, 2, 2)
        rows = [list(dst[r * 5 : r * 5 + 5]) for r in range(4)]
        assert rows == [
            [0xFFFF] * 5,
            [0xFFFF, 0xFFFF, 1, 2, 0xFFFF],
            [0xFFFF, 0xFFFF, 3, 4, 0xFFFF],
            [0xFFFF] * 5,
        ]

    def test_accepts_bytearrays(self):
        # The page passes raw RGB565 bytearrays/memoryviews, not arrays.
        src = bytearray(array.array("H", [7, 8, 9, 10]).tobytes())
        dst = bytearray(4 * 2)
        resample(src, 2, 2, dst, 2, 0, 0, 2, 2)
        assert array.array("H", bytes(dst)).tolist() == [7, 8, 9, 10]
