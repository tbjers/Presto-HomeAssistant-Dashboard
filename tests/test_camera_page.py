"""
Tests for dashboard.camera_page.CameraPage, with a fake MJPEGStream (see
tests/test_mjpeg.py for the stream itself) and the conftest jpegdec stub.
"""

from unittest import mock

import jpegdec
import picographics
import pytest
from tmos import Region

from dashboard import topics
from types import SimpleNamespace

from dashboard.camera_page import STALE_AFTER_MS, CameraPage, credentials_from_secrets
from dashboard.mjpeg import STATE_BACKOFF, STATE_STREAMING

REGION = Region(0, 52, 480, 428)
CAMERAS = [
    {"slug": "porch", "title": "Porch", "url": "http://10.0.0.5/a", "aspect": "16:9"},
    {"slug": "yard", "title": "Yard", "url": "http://10.0.0.6/a"},
]


class FakeStream:
    def __init__(self, url, user, password):
        self.url = url
        self.user = user
        self.password = password
        self.state = "idle"
        self.started = False
        self.stopped = False
        self.frames = []
        self.last_error = None

    def start(self):
        self.started = True
        self.state = STATE_STREAMING

    def stop(self):
        self.stopped = True
        self.state = "idle"

    def poll(self):
        return self.frames.pop(0) if self.frames else None


class Factory:
    def __init__(self):
        self.streams = []

    def __call__(self, url, user, password):
        stream = FakeStream(url, user, password)
        self.streams.append(stream)
        return stream


@pytest.fixture
def jpeg():
    decoder = mock.Mock()
    decoder.get_width.return_value = 704
    decoder.get_height.return_value = 480
    jpegdec.JPEG.reset_mock()
    jpegdec.JPEG.return_value = decoder
    with mock.patch.object(picographics, "PicoGraphics") as offscreen_cls:
        decoder.offscreen_cls = offscreen_cls
        yield decoder


def _window_manager(touch_factory):
    wm = mock.Mock()
    wm.theme.padding = 8
    wm.theme.measure_text.return_value = (40, 10)  # -> 26px title strip
    wm.display.get_bounds.return_value = (480, 480)
    wm.os.touch = touch_factory()
    return wm


def _page(user="viewer", cameras=CAMERAS):
    factory = Factory()
    mqtt = mock.Mock()
    page = CameraPage("Cameras", cameras, mqtt, lambda slug: (user, "pw"), stream_factory=factory)
    return page, factory, mqtt


def _shown(touch_factory, **kwargs):
    page, factory, mqtt = _page(**kwargs)
    wm = _window_manager(touch_factory)
    page.setup(REGION, wm)
    page._fb = bytearray(480 * 480 * 2)  # a Mock display has no buffer protocol
    page.will_show()
    return page, factory, mqtt, wm


class TestLifecycle:
    def test_title(self):
        page, _, _ = _page()
        assert page.title == "Cameras"

    def test_no_stream_until_shown(self):
        page, factory, _ = _page()
        assert factory.streams == []

    def test_will_show_starts_first_camera_with_secrets(self, mock_touch_factory, jpeg):
        _, factory, _, _ = _shown(mock_touch_factory)
        (stream,) = factory.streams
        assert stream.url == "http://10.0.0.5/a"
        assert (stream.user, stream.password) == ("viewer", "pw")
        assert stream.started

    def test_will_hide_stops_stream(self, mock_touch_factory, jpeg):
        page, factory, _, _ = _shown(mock_touch_factory)
        page.will_hide()
        assert factory.streams[0].stopped

    def test_teardown_stops_stream(self, mock_touch_factory, jpeg):
        # App switch: WindowManager.remove_page() -> teardown(), possibly
        # without will_hide().
        page, factory, _, _ = _shown(mock_touch_factory)
        page.teardown()
        assert factory.streams[0].stopped

    def test_no_stream_without_credentials(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory, user=None)
        page.tick(REGION, wm)
        assert factory.streams == []
        assert wm.update_display.called  # placeholder explains why


class TestCredentials:
    def test_per_camera_login_used_for_each_camera(self, mock_touch_factory, jpeg):
        secrets = SimpleNamespace(
            CAMERA_CREDENTIALS={"porch": ("p_user", "p_pw"), "yard": ("y_user", "y_pw")}
        )
        factory = Factory()
        page = CameraPage(
            "Cameras", CAMERAS, mock.Mock(), credentials_from_secrets(secrets), stream_factory=factory
        )
        page.setup(REGION, _window_manager(mock_touch_factory))
        page.will_show()
        page._open(1)
        assert [(s.user, s.password) for s in factory.streams] == [("p_user", "p_pw"), ("y_user", "y_pw")]

    def test_lookup_prefers_per_camera_entry(self):
        lookup = credentials_from_secrets(
            SimpleNamespace(
                CAMERA_USER="shared",
                CAMERA_PASSWORD="shared_pw",
                CAMERA_CREDENTIALS={"porch": ("p_user", "p_pw")},
            )
        )
        assert lookup("porch") == ("p_user", "p_pw")
        assert lookup("yard") == ("shared", "shared_pw")

    def test_lookup_shared_only(self):
        lookup = credentials_from_secrets(SimpleNamespace(CAMERA_USER="u", CAMERA_PASSWORD="p"))
        assert lookup("anything") == ("u", "p")

    def test_lookup_nothing_configured(self):
        assert credentials_from_secrets(SimpleNamespace())("porch") == (None, None)

    def test_malformed_entry_does_not_fall_back_to_shared(self):
        # A listed-but-broken entry is a config error to surface, not a
        # reason to try the shared login on that camera.
        lookup = credentials_from_secrets(
            SimpleNamespace(CAMERA_USER="shared", CAMERA_PASSWORD="pw", CAMERA_CREDENTIALS={"porch": "oops"})
        )
        assert lookup("porch") == (None, None)

    def test_camera_without_login_shows_message(self, mock_touch_factory, jpeg):
        page = CameraPage("Cameras", CAMERAS, mock.Mock(), lambda slug: (None, None), stream_factory=Factory())
        wm = _window_manager(mock_touch_factory)
        page.setup(REGION, wm)
        page.will_show()
        page.tick(REGION, wm)
        assert page._painted_status == "NO LOGIN IN SECRETS.PY"


class TestDrawing:
    def test_fits_16_9_frame_below_title_strip(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        factory.streams[0].frames.append(b"frame")

        with mock.patch("dashboard.camera_page.resample") as resample:
            page.tick(REGION, wm)

        # Area below the 26px strip: (0, 78, 480, 402); 16:9 at 480 wide is
        # 270 tall, centered -> y = 78 + (402 - 270) // 2 = 144.
        args = resample.call_args.args
        assert args[1:3] == (704, 480)  # full-size decode: half (352) < 480
        assert args[4:] == (480, 0, 144, 480, 270)
        jpeg.decode.assert_called_once_with(0, 0, jpegdec.JPEG_SCALE_FULL)
        wm.update_display.assert_called_with(REGION)

    def test_offscreen_buffer_sized_to_decoded_frame(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        factory.streams[0].frames.append(b"frame")

        page.tick(REGION, wm)

        _, kwargs = jpeg.offscreen_cls.call_args
        assert (kwargs["width"], kwargs["height"]) == (704, 480)
        assert len(kwargs["buffer"]) == 704 * 480 * 2
        jpegdec.JPEG.assert_called_with(jpeg.offscreen_cls.return_value)

    def test_offscreen_buffer_reused_across_frames(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        for _ in range(3):
            factory.streams[0].frames.append(b"frame")
            page.tick(REGION, wm)
        assert jpeg.offscreen_cls.call_count == 1

    def test_without_aspect_uses_frame_pixel_shape(self, mock_touch_factory, jpeg):
        cameras = [{"slug": "c", "url": "http://c/"}]
        page, factory, _, wm = _shown(mock_touch_factory, cameras=cameras)
        factory.streams[0].frames.append(b"frame")

        with mock.patch("dashboard.camera_page.resample") as resample:
            page.tick(REGION, wm)

        # 704x480 -> 480x327 in the 402px-tall area.
        assert resample.call_args.args[-2:] == (480, 327)

    def test_small_target_decodes_at_reduced_scale(self, mock_touch_factory, jpeg):
        jpeg.get_width.return_value = 1920
        jpeg.get_height.return_value = 1080
        page, factory, _, wm = _shown(mock_touch_factory)
        factory.streams[0].frames.append(b"frame")

        with mock.patch("dashboard.camera_page.resample") as resample:
            page.tick(REGION, wm)

        jpeg.decode.assert_called_once_with(0, 0, jpegdec.JPEG_SCALE_QUARTER)
        assert resample.call_args.args[1:3] == (480, 270)

    def test_idle_ticks_do_not_redraw(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        factory.streams[0].frames.append(b"frame")
        page.tick(REGION, wm)
        wm.update_display.reset_mock()

        page.tick(REGION, wm)
        page.tick(REGION, wm)

        assert jpeg.decode.call_count == 1
        wm.update_display.assert_not_called()

    def test_one_decode_per_frame(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        for _ in range(3):
            factory.streams[0].frames.append(b"frame")
            page.tick(REGION, wm)
        assert jpeg.decode.call_count == 3

    def test_stale_picture_triggers_one_status_redraw(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        factory.streams[0].frames.append(b"frame")
        page.tick(REGION, wm)
        wm.update_display.reset_mock()

        page._last_frame_ms -= STALE_AFTER_MS + 1
        page.tick(REGION, wm)
        page.tick(REGION, wm)

        assert wm.update_display.call_count == 1
        assert page._painted_status == "NO SIGNAL"

    def test_decode_error_is_reported_not_raised(self, mock_touch_factory, jpeg):
        jpeg.decode.side_effect = RuntimeError("bad jpeg")
        page, factory, mqtt, wm = _shown(mock_touch_factory)
        factory.streams[0].frames.append(b"frame")

        page.tick(REGION, wm)

        mqtt.report_error.assert_called_once()
        assert "render failed" in mqtt.report_error.call_args.args[2]


class TestFps:
    def _texts(self, wm):
        return [c.args[1] for c in wm.theme.text.call_args_list]

    def test_no_fps_until_two_frames(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        factory.streams[0].frames.append(b"frame")
        page.tick(REGION, wm)
        assert page.fps() is None
        assert not any("FPS" in t for t in self._texts(wm))

    def test_fps_shown_on_right_of_title_strip(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        clock = [0]
        with mock.patch("dashboard.camera_page.time.ticks_ms", lambda: clock[0]):
            for t in (0, 500, 1000):
                clock[0] = t
                factory.streams[0].frames.append(b"frame")
                page.tick(REGION, wm)
        assert page.fps() == pytest.approx(2.0)
        fps_call = [c for c in wm.theme.text.call_args_list if c.args[1] == "2.0 FPS"][-1]
        # Right-aligned: x = region right edge - padding - measured width (40).
        assert fps_call.args[2] == 480 - 8 - 40

    def test_fps_window_is_bounded(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        for _ in range(25):
            factory.streams[0].frames.append(b"frame")
            page.tick(REGION, wm)
        assert len(page._frame_times) == 10

    def test_status_replaces_fps(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        for _ in range(2):
            factory.streams[0].frames.append(b"frame")
            page.tick(REGION, wm)
        page._last_frame_ms -= STALE_AFTER_MS + 1
        wm.theme.text.reset_mock()
        page.tick(REGION, wm)
        texts = self._texts(wm)
        assert "NO SIGNAL" in texts
        assert not any("FPS" in t for t in texts)

    def test_switching_camera_resets_fps(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        for _ in range(2):
            factory.streams[0].frames.append(b"frame")
            page.tick(REGION, wm)
        page._open(1)
        assert page.fps() is None


class TestBacklight:
    def test_showing_disables_dim_and_sleep(self, mock_touch_factory, jpeg):
        page, _, _, wm = _shown(mock_touch_factory)
        held = wm.os.backlight_manager.display_timeouts
        assert (held.dim, held.sleep) == (0, 0)

    def test_hiding_restores_original_timeouts(self, mock_touch_factory, jpeg):
        page, factory, mqtt = _page()
        wm = _window_manager(mock_touch_factory)
        original = wm.os.backlight_manager.display_timeouts
        page.setup(REGION, wm)
        page.will_show()
        page.will_hide()
        assert wm.os.backlight_manager.display_timeouts is original

    def test_teardown_restores_original_timeouts(self, mock_touch_factory, jpeg):
        page, factory, mqtt = _page()
        wm = _window_manager(mock_touch_factory)
        original = wm.os.backlight_manager.display_timeouts
        page.setup(REGION, wm)
        page.will_show()
        page.teardown()
        assert wm.os.backlight_manager.display_timeouts is original

    def test_repeated_show_keeps_the_real_original(self, mock_touch_factory, jpeg):
        page, factory, mqtt = _page()
        wm = _window_manager(mock_touch_factory)
        original = wm.os.backlight_manager.display_timeouts
        page.setup(REGION, wm)
        page.will_show()
        page.will_show()
        page.will_hide()
        assert wm.os.backlight_manager.display_timeouts is original

    def test_hide_then_teardown_restores_once(self, mock_touch_factory, jpeg):
        page, factory, mqtt = _page()
        wm = _window_manager(mock_touch_factory)
        original = wm.os.backlight_manager.display_timeouts
        page.setup(REGION, wm)
        page.will_show()
        page.will_hide()
        replaced = object()
        wm.os.backlight_manager.display_timeouts = replaced  # e.g. another page's change
        page.teardown()
        assert wm.os.backlight_manager.display_timeouts is replaced


class TestErrors:
    def test_stream_error_reported_once_per_open(self, mock_touch_factory, jpeg):
        page, factory, mqtt, wm = _shown(mock_touch_factory)
        stream = factory.streams[0]
        stream.state = STATE_BACKOFF
        stream.last_error = "StreamError: 401: camera rejected the credentials"

        page.tick(REGION, wm)
        page.tick(REGION, wm)

        mqtt.report_error.assert_called_once_with(
            topics.ERROR_LEVEL_WARNING, "camera", "porch: StreamError: 401: camera rejected the credentials"
        )
        assert page._painted_status == "LOGIN FAILED"


class TestTouch:
    def _tap(self, page, wm, x, y):
        wm.os.touch.state, wm.os.touch.x, wm.os.touch.y = True, x, y
        page.tick(REGION, wm)
        wm.os.touch.state = False
        page.tick(REGION, wm)

    def test_tap_cycles_to_next_camera(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)

        self._tap(page, wm, 200, 200)

        assert factory.streams[0].stopped
        assert factory.streams[1].url == "http://10.0.0.6/a"
        assert page.camera["slug"] == "yard"

    def test_tap_wraps_around(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory)
        self._tap(page, wm, 200, 200)
        self._tap(page, wm, 200, 200)
        assert page.camera["slug"] == "porch"

    def test_touch_outside_region_is_ignored(self, mock_touch_factory, jpeg):
        # e.g. a systray tap: the page still ticks while the finger is down.
        page, factory, _, wm = _shown(mock_touch_factory)
        self._tap(page, wm, 200, 10)
        assert len(factory.streams) == 1

    def test_single_camera_does_not_reconnect_on_tap(self, mock_touch_factory, jpeg):
        page, factory, _, wm = _shown(mock_touch_factory, cameras=CAMERAS[:1])
        self._tap(page, wm, 200, 200)
        assert len(factory.streams) == 1
