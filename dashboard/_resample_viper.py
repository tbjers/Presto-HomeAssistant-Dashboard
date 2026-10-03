# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Viper (native-speed) RGB565 nearest-neighbour resampler for
dashboard/resample.py. Device-only: importing it on CPython fails at
`import micropython`, and dashboard/resample.py then falls back to its
pure-Python twin, which the host tests exercise. The two must stay
pixel-identical (scripts/camera_smoke_test.py compares them on-device).

`@micropython.viper` is resolved by the MicroPython compiler, not looked
up at runtime -- `hasattr(micropython, "viper")` is False on the Presto
even though the decorator works.
"""

import micropython


@micropython.viper
def resample(src_buf, src_w: int, src_h: int, dst_buf, dst_stride: int,
             dx: int, dy: int, dw: int, dh: int):
    src = ptr16(src_buf)
    dst = ptr16(dst_buf)
    step_x = (src_w << 16) // dw
    y = 0
    while y < dh:
        src_row = ((y * src_h) // dh) * src_w
        dst_row = (dy + y) * dst_stride + dx
        acc = 0
        x = 0
        while x < dw:
            dst[dst_row + x] = src[src_row + (acc >> 16)]
            acc += step_x
            x += 1
        y += 1
