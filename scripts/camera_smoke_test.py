# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
On-device gating probe for camera screens: reads a camera's MJPEG stream
directly via dashboard.mjpeg.MJPEGStream and renders it the way
dashboard/camera_page.py does. Run via

    mpremote cp dashboard/md5.py dashboard/mjpeg.py dashboard/resample.py \\
        dashboard/_resample_viper.py :dashboard/
    mpremote run scripts/camera_smoke_test.py

Needs CAMERA_USER / CAMERA_PASSWORD in the on-device secrets.py (add them
there by hand -- don't cp a placeholder over it). Edit STREAM_URL / ASPECT
below for a different camera. Does not touch flash/main.py; see
scripts/device_error_smoke_test.py for the WDT caveat (feed_wdt() below
re-arms + feeds defensively).

Checks host-side pytest cannot:

1. jpegdec exists; heap size; the viper resample build gives the same
   pixels as tests/test_resample.py expects of the pure-Python twin.
2. Digest auth against the real camera succeeds using dashboard/md5.py
   (the firmware's hashlib has no md5).
3. The stream's multipart framing: prints the start of the stream so you
   can see whether parts carry Content-Length (the fast path) and what the
   boundary is.
4. Frames arrive at the camera's rate through non-blocking polls, and how
   long each poll() blocks.
5. The page's render path: decode into an off-screen DISPLAY_GENERIC
   buffer, then viper-resample into the framebuffer at the aspect-corrected
   fit -- and how long each half takes.
"""

import gc
import time

from tmos import OS

import picographics
import secrets

from dashboard import mjpeg
from dashboard.resample import decode_shift, fit_rect, parse_aspect, resample

STREAM_URL = "http://192.168.1.108/cgi-bin/mjpg/video.cgi?channel=1&subtype=1"  # edit: your camera
ASPECT = "16:9"
RUN_MS = 12000
# Stand-in for the page's picture area: content region minus systray and
# the camera page's title strip.
AREA = (0, 78, 480, 402)


def feed_wdt():
    try:
        from machine import WDT

        WDT(timeout=8388).feed()
    except Exception:  # noqa: BLE001
        pass


def check_resample():
    # Same expectation as tests/test_resample.py, against the device build.
    import array

    src = array.array("H", [y * 10 + x for y in range(4) for x in range(4)])
    dst = array.array("H", [0] * 4)
    resample(src, 4, 4, dst, 2, 0, 0, 2, 2)
    ok = list(dst) == [0, 2, 20, 22]
    print("  resample =", resample)
    print("  resample pixel check:", "ok" if ok else "MISMATCH {}".format(list(dst)))


def main():
    feed_wdt()
    print("--- 1. jpegdec + heap + resample ---")
    import jpegdec

    gc.collect()
    print("  gc.mem_free() =", gc.mem_free())
    check_resample()

    print("connecting wifi...")
    os = OS(layers=1, full_res=True)
    os.boot(wifi=True, use_ntp=False, run=False)
    feed_wdt()
    print("wifi connected\n")

    print("--- 2. digest auth ---")
    stream = mjpeg.MJPEGStream(STREAM_URL, secrets.CAMERA_USER, secrets.CAMERA_PASSWORD)
    stream.start()
    for _ in range(2):
        t0 = time.ticks_ms()
        stream.poll()
        print("  step -> state={} ({}ms) error={}".format(
            stream.state, time.ticks_diff(time.ticks_ms(), t0), stream.last_error))
        feed_wdt()
    if stream.state != mjpeg.STATE_STREAMING:
        print("  ! not streaming -- stopping here")
        return
    print("  boundary =", stream._boundary)

    print("\n--- 3. stream framing (first bytes after the HTTP headers) ---")
    deadline = time.ticks_add(time.ticks_ms(), 3000)
    while stream._fill - stream._consumed < 200 and time.ticks_diff(deadline, time.ticks_ms()) > 0:
        n = stream._sock.readinto(stream._view[stream._fill :])
        if n:
            stream._fill += n
        time.sleep_ms(20)
    head = bytes(stream._view[stream._consumed : stream._consumed + 200])
    print("  ", head[: head.find(b"\xff\xd8") if b"\xff\xd8" in head else 200])

    print("\n--- 4/5. frames over {}s, rendered like CameraPage ---".format(RUN_MS // 1000))
    display = os.display
    fb = memoryview(display)
    display_w = display.get_bounds()[0]
    scales = (
        jpegdec.JPEG_SCALE_FULL,
        jpegdec.JPEG_SCALE_HALF,
        jpegdec.JPEG_SCALE_QUARTER,
        jpegdec.JPEG_SCALE_EIGHTH,
    )
    jpeg = jpegdec.JPEG(display)
    off_buf, off_size = None, None
    display.set_pen(display.create_pen(0, 0, 0))
    display.clear()
    os.update_display()
    start = time.ticks_ms()
    worst_poll = 0
    last_frame_at = None
    decoded = 0
    busy_ms = 0
    worst_render = 0
    while time.ticks_diff(time.ticks_ms(), start) < RUN_MS:
        feed_wdt()
        t0 = time.ticks_ms()
        frame = stream.poll()
        worst_poll = max(worst_poll, time.ticks_diff(time.ticks_ms(), t0))
        if frame is not None:
            now = time.ticks_ms()
            gap = time.ticks_diff(now, last_frame_at) if last_frame_at is not None else 0
            last_frame_at = now
            t1 = time.ticks_ms()
            jpeg.open_RAM(frame)
            w, h = jpeg.get_width(), jpeg.get_height()
            rect = fit_rect(AREA, w, h, parse_aspect(ASPECT))
            shift = decode_shift(w, h, rect[2], rect[3])
            size = (-(-w >> shift), -(-h >> shift))
            if size != off_size:
                off_buf = bytearray(size[0] * size[1] * 2)
                off = picographics.PicoGraphics(
                    picographics.DISPLAY_GENERIC, width=size[0], height=size[1],
                    pen_type=picographics.PEN_RGB565, buffer=off_buf)
                jpeg = jpegdec.JPEG(off)
                off_size = size
                jpeg.open_RAM(frame)
            jpeg.decode(0, 0, scales[shift])
            t2 = time.ticks_ms()
            resample(off_buf, size[0], size[1], fb, display_w, *rect)
            t3 = time.ticks_ms()
            os.update_display()
            t4 = time.ticks_ms()
            frame_len = len(frame)
            frame = None
            gc.collect()
            t5 = time.ticks_ms()
            decoded += 1
            render = time.ticks_diff(t5, t1)
            busy_ms += render
            worst_render = max(worst_render, render)
            print("  frame {}B {}x{} -> {} gap={}ms decode={} resample={} flip={} gc={} total={}ms".format(
                frame_len, w, h, rect, gap, time.ticks_diff(t2, t1), time.ticks_diff(t3, t2),
                time.ticks_diff(t4, t3), time.ticks_diff(t5, t4), render))
        if stream.state != mjpeg.STATE_STREAMING:
            print("  ! stream dropped:", stream.last_error)
            break
        # Like TmOS's scheduler for a 10Hz page task: next tick 100ms after
        # this one started, or immediately if rendering overran that.
        wait = 100 - time.ticks_diff(time.ticks_ms(), t0)
        if wait > 0:
            time.sleep_ms(wait)
    elapsed = time.ticks_diff(time.ticks_ms(), start)
    stream.stop()
    print("  rendered {} of {} frames received ({} skipped) in {}s = {:.1f} fps shown".format(
        decoded, stream.parts, stream.parts - decoded, elapsed // 1000, decoded * 1000 / elapsed))
    print("  busy rendering {}% of the time; worst render {}ms; worst poll() {}ms".format(
        busy_ms * 100 // elapsed, worst_render, worst_poll))
    gc.collect()
    print("  gc.mem_free() =", gc.mem_free())


main()
