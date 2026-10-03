# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
CameraPage(Page) -- a full-page live view of one camera at a time, reading
the camera's own MJPEG stream (dashboard/mjpeg.py) rather than anything
relayed over MQTT. The config topic carries only each camera's slug, title
and stream URL; the login comes from the on-device secrets.py
(CAMERA_USER/CAMERA_PASSWORD).

Each frame is fitted (never cropped) into the page below a title strip, at
the camera's true display aspect -- config "aspect", e.g. "16:9" for a
Dahua D1 substream, which squeezes a 16:9 sensor into 704x480. jpegdec
can't scale arbitrarily, so frames are decoded into an off-screen RGB565
buffer and resampled into the framebuffer (dashboard/resample.py). Measured
for 704x480 -> 480x400: ~470ms decode + ~155ms resample.

Like the modals (dashboard/modal.py's redraw_on_demand), tick() never
repaints unconditionally: at the page's 10Hz it polls the stream (cheap, non-
blocking) and only decodes + flips when a new frame arrives or the status
line changes. A frame render is the longest stall in this app (~0.6s),
still far inside the ~8s watchdog. There is deliberately no gc.collect()
per frame: the stream and decode buffers are preallocated and reused, so a
frame only makes a few small objects, and a forced collect of the ~8MB heap
cost ~49ms a frame (measured) -- MicroPython's own collector runs when needed.

While the page is visible, TmOS's backlight dim/sleep timeouts are held off
(set to 0, which BacklightManager treats as disabled) -- a live view
shouldn't fade out -- and restored on will_hide()/teardown(). Leaving the
page takes a touch, which resets the inactivity timer, so the restored
timeouts start fresh rather than firing immediately.

The stream is open only while the page is visible: will_show() starts it,
will_hide() *and* teardown() stop it -- an app switch (e.g. to Settings)
removes pages via WindowManager.remove_page(), which calls teardown()
without necessarily calling will_hide() first. Tapping the page cycles to
the next camera.
"""

import gc
import time

import jpegdec
import picographics
from tmos import BacklightManager
from tmos_ui import Page, is_within

from dashboard import palette, topics
from dashboard.mjpeg import STATE_BACKOFF, MJPEGStream
from dashboard.palette import PenCache
from dashboard.resample import decode_shift, fit_rect, parse_aspect, resample

# No new frame for this long while connected -> flag the picture as stale.
STALE_AFTER_MS = 5000
# The FPS readout averages over the last this-many frames.
FPS_WINDOW = 10

_SCALES = (
    jpegdec.JPEG_SCALE_FULL,
    jpegdec.JPEG_SCALE_HALF,
    jpegdec.JPEG_SCALE_QUARTER,
    jpegdec.JPEG_SCALE_EIGHTH,
)


def _framebuffer(display):
    # PicoGraphics exposes its RGB565 framebuffer via the buffer protocol
    # (confirmed on the Presto: 480*480*2 bytes with layers=1).
    try:
        return memoryview(display)
    except TypeError:
        return None


class CameraPage(Page):
    execution_frequency = 10

    def __init__(self, title, cameras, mqtt, user, password, stream_factory=MJPEGStream):
        super().__init__()
        self.title = title
        self._cameras = cameras
        self._mqtt = mqtt
        self._user = user
        self._password = password
        self._stream_factory = stream_factory
        self._index = 0
        self._stream = None
        self._jpeg = None
        self._pens = None
        self._fb = None
        self._os = None
        self._saved_timeouts = None
        self._display_w = 0
        self._offscreen = None
        self._offscreen_buf = None
        self._offscreen_size = None
        self._painted_rect = None
        self._showing_frame = False
        self._last_frame_ms = None
        self._frame_times = []
        self._painted_status = None
        self._needs_full_clear = True
        self._reported_error = False
        self._touch_started_inside = False
        self._was_touched = False

    # -- lifecycle ----------------------------------------------------------

    def setup(self, region, window_manager):
        display = window_manager.display
        self._os = window_manager.os
        self._pens = PenCache(display)
        self._fb = _framebuffer(display)
        self._display_w = display.get_bounds()[0]
        self._needs_full_clear = True

    def will_show(self):
        self._hold_backlight()
        self._open(self._index)

    def will_hide(self):
        self._close()
        self._release_backlight()

    def teardown(self):
        self._close()
        self._release_backlight()
        super().teardown()

    def _hold_backlight(self):
        if self._os is None or self._saved_timeouts is not None:
            return
        manager = self._os.backlight_manager
        self._saved_timeouts = manager.display_timeouts
        held = BacklightManager.TimeoutSettings()
        held.dim = 0
        held.sleep = 0
        manager.display_timeouts = held

    def _release_backlight(self):
        if self._saved_timeouts is None:
            return
        self._os.backlight_manager.display_timeouts = self._saved_timeouts
        self._saved_timeouts = None

    @property
    def camera(self):
        return self._cameras[self._index]

    def _open(self, index):
        self._close()
        self._index = index % len(self._cameras)
        self._showing_frame = False
        self._last_frame_ms = None
        self._frame_times = []
        self._painted_status = None
        self._painted_rect = None
        self._needs_full_clear = True
        self._reported_error = False
        if not self._user:
            return
        try:
            self._stream = self._stream_factory(self.camera["url"], self._user, self._password)
        except ValueError:
            self._stream = None
            return
        self._stream.start()

    def _close(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream = None

    # -- tick ---------------------------------------------------------------

    def tick(self, region, window_manager):
        self._handle_touch(region, window_manager.os.touch)

        frame = self._stream.poll() if self._stream is not None else None
        now = time.ticks_ms()
        if frame is not None:
            self._last_frame_ms = now
            self._frame_times.append(now)
            if len(self._frame_times) > FPS_WINDOW:
                self._frame_times.pop(0)
        self._maybe_report_error()

        status = self._status(now)
        if frame is None and status == self._painted_status and not self._needs_full_clear:
            return

        display = window_manager.display
        theme = window_manager.theme
        if self._needs_full_clear or (frame is None and not self._showing_frame):
            theme.clear_display(display, region)
            self._needs_full_clear = False
        if frame is not None:
            self._render(frame, display, region, theme)
        if self._showing_frame:
            self._draw_overlay(display, region, theme, status)
        else:
            self._draw_placeholder(display, region, theme, status)
        self._painted_status = status
        window_manager.update_display(region)

    def _handle_touch(self, region, touch):
        touched = touch.state
        if touched and not self._was_touched:
            self._touch_started_inside = is_within(region, touch.x, touch.y)
        elif not touched and self._was_touched:
            if self._touch_started_inside and len(self._cameras) > 1:
                self._open(self._index + 1)
            self._touch_started_inside = False
        self._was_touched = touched

    def _status(self, now):
        if not self._user:
            return "SET CAMERA_USER IN SECRETS.PY"
        if self._stream is None:
            return "BAD CAMERA URL"
        if self._stream.state == STATE_BACKOFF:
            if "credentials" in (self._stream.last_error or ""):
                return "LOGIN FAILED"
            return "NO CONNECTION"
        if self._last_frame_ms is None:
            return "CONNECTING"
        if time.ticks_diff(now, self._last_frame_ms) > STALE_AFTER_MS:
            return "NO SIGNAL"
        return None

    def _maybe_report_error(self):
        # Once per camera/open: a camera that's off or rejecting the login
        # would otherwise re-report on every backoff retry.
        if self._reported_error or self._stream is None or self._stream.state != STATE_BACKOFF:
            return
        self._reported_error = True
        self._mqtt.report_error(
            topics.ERROR_LEVEL_WARNING,
            "camera",
            "{}: {}".format(self.camera.get("slug"), self._stream.last_error),
        )

    # -- drawing ------------------------------------------------------------

    def _strip_height(self, display, theme):
        _, text_h = theme.measure_text(display, "X")
        return text_h + 2 * theme.padding

    def _render(self, frame, display, region, theme):
        try:
            self._ensure_decoder(display)
            self._jpeg.open_RAM(frame)
            frame_w, frame_h = self._jpeg.get_width(), self._jpeg.get_height()
            strip_h = self._strip_height(display, theme)
            area = (region.x, region.y + strip_h, region.width, region.height - strip_h)
            rect = fit_rect(area, frame_w, frame_h, parse_aspect(self.camera.get("aspect")))
            shift = decode_shift(frame_w, frame_h, rect[2], rect[3])
            size = (-(-frame_w >> shift), -(-frame_h >> shift))  # ceil
            if size != self._offscreen_size:
                self._allocate_offscreen(size)
                self._jpeg.open_RAM(frame)
            self._jpeg.decode(0, 0, _SCALES[shift])
            if rect != self._painted_rect:
                # New geometry (first frame, or the camera changed size):
                # repaint the letterbox bars around the picture.
                theme.clear_display(display, region)
                self._painted_rect = rect
            resample(self._offscreen_buf, size[0], size[1], self._fb, self._display_w, *rect)
            self._showing_frame = True
        except Exception as exc:  # noqa: BLE001 -- one bad JPEG must not kill the run loop
            if not self._reported_error:
                self._reported_error = True
                self._mqtt.report_error(
                    topics.ERROR_LEVEL_WARNING,
                    "camera",
                    "{}: render failed: {}".format(self.camera.get("slug"), exc),
                )

    def _ensure_decoder(self, display):
        if self._fb is None:
            raise RuntimeError("display framebuffer unavailable")
        if self._jpeg is None:
            # Bound to the real display just to read frame dimensions; the
            # first decode reallocates it onto an off-screen buffer.
            self._jpeg = jpegdec.JPEG(display)

    def _allocate_offscreen(self, size):
        # Drop the old buffer first so the heap can reuse it (~0.7MB for
        # a full D1 frame).
        self._offscreen = None
        self._offscreen_buf = None
        gc.collect()
        width, height = size
        self._offscreen_buf = bytearray(width * height * 2)
        self._offscreen = picographics.PicoGraphics(
            picographics.DISPLAY_GENERIC,
            width=width,
            height=height,
            pen_type=picographics.PEN_RGB565,
            buffer=self._offscreen_buf,
        )
        self._jpeg = jpegdec.JPEG(self._offscreen)
        self._offscreen_size = size

    def _label(self):
        return self.camera.get("title") or self.camera.get("slug", "")

    def fps(self):
        """Frames shown per second over the last FPS_WINDOW frames, or None
        until there are two to measure between."""
        times = self._frame_times
        if len(times) < 2:
            return None
        span = time.ticks_diff(times[-1], times[0])
        if span <= 0:
            return None
        return (len(times) - 1) * 1000 / span

    def _draw_overlay(self, display, region, theme, status):
        # A strip across the top of the page, above the picture: camera
        # title on the left; on the right the status (e.g. NO SIGNAL) when
        # there is one, otherwise the measured frame rate. Redrawn with
        # every frame, so the FPS readout stays current.
        pad = theme.padding
        strip_h = self._strip_height(display, theme)
        display.set_pen(self._pens.get(palette.BLACK))
        display.rectangle(region.x, region.y, region.width, strip_h)
        display.set_pen(self._pens.get(palette.GRAY_200))
        theme.text(display, self._label(), region.x + pad, region.y + pad)
        if status:
            right, color = status, palette.AMBER_400
        else:
            fps = self.fps()
            right, color = ("{:.1f} FPS".format(fps) if fps else ""), palette.GRAY_500
        if right:
            right_w, _ = theme.measure_text(display, right)
            display.set_pen(self._pens.get(color))
            theme.text(display, right, region.x + region.width - pad - right_w, region.y + pad)

    def _draw_placeholder(self, display, region, theme, status):
        label = self._label()
        status = status or ""
        label_w, text_h = theme.measure_text(display, label, rel_scale=2)
        status_w, _ = theme.measure_text(display, status)
        cy = region.y + region.height // 2
        display.set_pen(self._pens.get(palette.GRAY_200))
        theme.text(display, label, region.x + (region.width - label_w) // 2, cy - text_h - theme.padding, rel_scale=2)
        display.set_pen(self._pens.get(palette.GRAY_500))
        theme.text(display, status, region.x + (region.width - status_w) // 2, cy + theme.padding)
