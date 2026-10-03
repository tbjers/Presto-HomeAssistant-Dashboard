# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Frame geometry + scaling for dashboard/camera_page.py.

jpegdec can only downscale by 1/2, 1/4 or 1/8, so fitting a camera frame to
an arbitrary page area (and correcting its aspect: a Dahua D1 substream is
a 16:9 sensor squeezed into 704x480) takes two steps: decode into an
off-screen RGB565 buffer at the largest power-of-two scale that is still
>= the target size (decode_shift), then nearest-neighbour resample that
into the display's framebuffer (resample).

Measured on hardware for 704x480 -> 480x400: ~470ms decode + ~155ms
resample (viper). resample writes straight into the framebuffer, bypassing
PicoGraphics' clip, so callers must keep the target rect inside their
region -- fit_rect() does by construction.
"""

try:
    from dashboard._resample_viper import resample
except ImportError:  # CPython (host tests): no `micropython` module

    def resample(src_buf, src_w, src_h, dst_buf, dst_stride, dx, dy, dw, dh):
        """Pure-Python twin of _resample_viper.resample -- same integer
        math, so both produce identical pixels."""
        src = memoryview(src_buf).cast("B").cast("H")
        dst = memoryview(dst_buf).cast("B").cast("H")
        step_x = (src_w << 16) // dw
        for y in range(dh):
            src_row = ((y * src_h) // dh) * src_w
            dst_row = (dy + y) * dst_stride + dx
            acc = 0
            for x in range(dw):
                dst[dst_row + x] = src[src_row + (acc >> 16)]
                acc += step_x


def parse_aspect(value):
    """Display aspect ratio (width / height) from a camera config value:
    "16:9", "4:3", or a plain number. None if absent or unusable, meaning
    "use the frame's own pixel shape"."""
    if value is None:
        return None
    try:
        if isinstance(value, str) and ":" in value:
            w, h = value.split(":", 1)
            ratio = float(w) / float(h)
        else:
            ratio = float(value)
    except (ValueError, ZeroDivisionError):
        return None
    return ratio if ratio > 0 else None


def fit_rect(area, frame_w, frame_h, aspect=None):
    """The largest rect of display aspect `aspect` (default: frame_w /
    frame_h) that fits inside `area` (x, y, w, h), centered in it."""
    ax, ay, aw, ah = area
    if aspect is None:
        aspect = frame_w / frame_h
    tw = aw
    th = int(aw / aspect + 0.5)
    if th > ah:
        th = ah
        tw = min(aw, int(ah * aspect + 0.5))
    return ax + (aw - tw) // 2, ay + (ah - th) // 2, tw, th


def decode_shift(frame_w, frame_h, target_w, target_h):
    """Largest power-of-two downscale (as a shift: 0 = full, 1 = 1/2,
    2 = 1/4, 3 = 1/8) whose decoded size still covers the target, so
    resample only ever shrinks or barely stretches."""
    for shift in (3, 2, 1):
        if frame_w >> shift >= target_w and frame_h >> shift >= target_h:
            return shift
    return 0
