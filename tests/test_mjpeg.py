"""
Tests for dashboard.md5 and dashboard.mjpeg.

MJPEGStream is driven against scripted fake sockets: a challenge
connection that answers 401 + Digest, then a stream connection that hands
out pre-chunked multipart bytes (None = "nothing pending", the MicroPython
non-blocking convention; b"" = peer closed).
"""

import hashlib
import os

import pytest

from dashboard import mjpeg
from dashboard.md5 import md5_hex
from dashboard.mjpeg import (
    STATE_AUTH,
    STATE_BACKOFF,
    STATE_CHALLENGE,
    STATE_IDLE,
    STATE_STREAMING,
    MJPEGStream,
    digest_authorization,
    parse_challenge,
    parse_url,
)

URL = "http://10.0.0.5/cgi-bin/mjpg/video.cgi?channel=1&subtype=1"
PATH = "/cgi-bin/mjpg/video.cgi?channel=1&subtype=1"
CHALLENGE_RESPONSE = (
    b"HTTP/1.1 401 Unauthorized\r\n"
    b'WWW-Authenticate: Digest realm="Login to cam", qop="auth", nonce="123", '
    b'opaque="abc", algorithm=MD5\r\n'
    b"Connection: close\r\nCONTENT-LENGTH: 0\r\n\r\n"
)
STREAM_HEADERS = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: multipart/x-mixed-replace; boundary=myboundary\r\n\r\n"
)


def _part(jpeg, content_length=True):
    headers = b"--myboundary\r\nContent-Type: image/jpeg\r\n"
    if content_length:
        headers += b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n"
    return headers + b"\r\n" + jpeg + b"\r\n"


def _jpeg(n, fill=0x11):
    return b"\xff\xd8" + bytes([fill]) * n + b"\xff\xd9"


class FakeSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.written = b""
        self.closed = False
        self.timeout = "unset"

    def write(self, data):
        self.written += data

    def settimeout(self, value):
        self.timeout = value

    def readinto(self, view):
        if not self.chunks:
            return None
        chunk = self.chunks[0]
        if chunk is None:
            self.chunks.pop(0)
            return None
        if isinstance(chunk, Exception):
            self.chunks.pop(0)
            raise chunk
        if chunk == b"":  # peer closed
            return 0
        n = min(len(view), len(chunk))
        view[:n] = chunk[:n]
        if n == len(chunk):
            self.chunks.pop(0)
        else:
            self.chunks[0] = chunk[n:]
        return n

    def close(self):
        self.closed = True


class FakeConnector:
    def __init__(self, *sockets):
        self.sockets = list(sockets)
        self.calls = []

    def __call__(self, host, port):
        self.calls.append((host, port))
        return self.sockets.pop(0)


def _streaming(stream_chunks, buffer_size=4096):
    challenge = FakeSocket([CHALLENGE_RESPONSE])
    stream = FakeSocket([STREAM_HEADERS] + list(stream_chunks))
    connector = FakeConnector(challenge, stream)
    s = MJPEGStream(URL, "viewer", "secret", connect=connector, buffer_size=buffer_size)
    s.start()
    s.poll()  # challenge
    s.poll()  # authenticated GET
    assert s.state == STATE_STREAMING, s.last_error
    return s, challenge, stream, connector


class TestMD5:
    @pytest.mark.parametrize("size", [0, 1, 55, 56, 63, 64, 65, 127, 1000])
    def test_matches_hashlib(self, size):
        data = os.urandom(size)
        assert md5_hex(data) == hashlib.md5(data).hexdigest()

    def test_accepts_str(self):
        assert md5_hex("abc") == "900150983cd24fb0d6963f7d28e17f72"


class TestDigest:
    def test_rfc2617_worked_example(self):
        # RFC 2617 section 3.5.
        challenge = parse_challenge(
            'Digest realm="testrealm@host.com", qop="auth,auth-int", '
            'nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", opaque="5ccc069c403ebaf9f0171e9517f40e41"'
        )
        header = digest_authorization(
            "Mufasa", "Circle Of Life", "GET", "/dir/index.html", challenge, "0a4f113b"
        )
        assert 'response="6629fae49393a05397450978507c4ef1"' in header
        assert "qop=auth" in header
        assert "nc=00000001" in header
        assert 'opaque="5ccc069c403ebaf9f0171e9517f40e41"' in header

    def test_parse_dahua_challenge(self):
        value = (
            'Digest realm="Login to d6010f52", qop="auth", nonce="1836821331", '
            'opaque="3e2e98", algorithm=MD5'
        )
        assert parse_challenge(value) == {
            "realm": "Login to d6010f52",
            "qop": "auth",
            "nonce": "1836821331",
            "opaque": "3e2e98",
            "algorithm": "MD5",
        }

    def test_parse_challenge_rejects_basic(self):
        assert parse_challenge('Basic realm="x"') is None

    def test_without_qop_uses_legacy_response(self):
        header = digest_authorization("u", "p", "GET", "/", {"realm": "r", "nonce": "n"}, "c")
        ha1, ha2 = md5_hex("u:r:p"), md5_hex("GET:/")
        assert 'response="{}"'.format(md5_hex("{}:n:{}".format(ha1, ha2))) in header
        assert "qop" not in header


class TestParseUrl:
    def test_default_port_and_query(self):
        assert parse_url(URL) == ("10.0.0.5", 80, PATH)

    def test_explicit_port(self):
        assert parse_url("http://cam:8080/x") == ("cam", 8080, "/x")

    def test_rejects_https(self):
        with pytest.raises(ValueError):
            parse_url("https://cam/x")


class TestHandshake:
    def test_idle_until_started(self):
        connector = FakeConnector()
        s = MJPEGStream(URL, "u", "p", connect=connector, buffer_size=1024)
        assert s.poll() is None
        assert s.state == STATE_IDLE
        assert connector.calls == []

    def test_challenge_then_authenticated_request(self):
        s, challenge, stream, connector = _streaming([])
        assert connector.calls == [("10.0.0.5", 80), ("10.0.0.5", 80)]
        assert challenge.closed
        assert b"Authorization" not in challenge.written
        assert challenge.written.startswith(b"GET " + PATH.encode() + b" HTTP/1.1\r\n")
        request = stream.written.decode()
        assert 'uri="{}"'.format(PATH) in request
        assert 'nonce="123"' in request
        assert 'opaque="abc"' in request
        assert stream.timeout == 0  # non-blocking once streaming

    def test_one_connection_step_per_poll(self):
        challenge = FakeSocket([CHALLENGE_RESPONSE])
        connector = FakeConnector(challenge, FakeSocket([STREAM_HEADERS]))
        s = MJPEGStream(URL, "u", "p", connect=connector, buffer_size=1024)
        s.start()
        assert s.state == STATE_CHALLENGE
        s.poll()
        assert s.state == STATE_AUTH
        assert len(connector.calls) == 1

    def test_rejected_credentials_back_off(self):
        rejected = FakeSocket([CHALLENGE_RESPONSE])
        connector = FakeConnector(FakeSocket([CHALLENGE_RESPONSE]), rejected)
        s = MJPEGStream(URL, "u", "wrong", connect=connector, buffer_size=1024)
        s.start()
        s.poll()
        s.poll()
        assert s.state == STATE_BACKOFF
        assert "rejected the credentials" in s.last_error
        assert rejected.closed

    def test_connect_error_backs_off_with_growing_delay(self):
        def refuse(host, port):
            raise OSError(113)

        s = MJPEGStream(URL, "u", "p", connect=refuse, buffer_size=1024)
        s.start()
        s.poll()
        assert s.state == STATE_BACKOFF
        assert s._backoff_ms == mjpeg.MIN_BACKOFF_MS * 2

    def test_backoff_retries_with_fresh_challenge_when_due(self):
        s = MJPEGStream(URL, "u", "p", connect=lambda h, p: (_ for _ in ()).throw(OSError(1)), buffer_size=1024)
        s.start()
        s.poll()
        s._retry_at = 0
        s.poll()
        assert s.state == STATE_CHALLENGE

    def test_stop_closes_socket(self):
        s, _, stream, _ = _streaming([])
        s.stop()
        assert stream.closed
        assert s.state == STATE_IDLE


class TestFrames:
    def test_returns_complete_frame(self):
        jpeg = _jpeg(100)
        s, *_ = _streaming([_part(jpeg)])
        frame = s.poll()
        assert bytes(frame) == jpeg

    def test_incomplete_frame_waits_for_more(self):
        part = _part(_jpeg(300))
        s, *_ = _streaming([part[:150], None, part[150:]])
        assert s.poll() is None
        assert bytes(s.poll()) == _jpeg(300)

    def test_only_newest_of_several_frames(self):
        a, b, c = _jpeg(50, 0x01), _jpeg(50, 0x02), _jpeg(50, 0x03)
        s, *_ = _streaming([_part(a) + _part(b) + _part(c)])
        assert bytes(s.poll()) == c

    def test_frame_split_across_polls_with_compaction(self):
        # Buffer smaller than two parts: forces _compact() between frames.
        a, b = _jpeg(1500, 0x01), _jpeg(1500, 0x02)
        s, *_ = _streaming([_part(a), None, _part(b)], buffer_size=2048)
        assert bytes(s.poll()) == a
        assert bytes(s.poll()) == b

    def test_falls_back_to_boundary_without_content_length(self):
        a, b = _jpeg(80, 0x01), _jpeg(80, 0x02)
        s, *_ = _streaming([_part(a, content_length=False) + _part(b, content_length=False)])
        # b has no terminating boundary yet, so a is the newest complete one.
        assert bytes(s.poll()) == a

    def test_frame_bodies_may_contain_soi_eoi_bytes(self):
        # An EXIF thumbnail embeds its own FFD8..FFD9; Content-Length framing
        # must not be fooled by it.
        jpeg = b"\xff\xd8" + b"\xff\xd8thumb\xff\xd9" + b"\x22" * 40 + b"\xff\xd9"
        s, *_ = _streaming([_part(jpeg)])
        assert bytes(s.poll()) == jpeg

    def test_oversized_frame_fails_and_backs_off(self):
        s, _, stream, _ = _streaming([_part(_jpeg(5000))], buffer_size=2048)
        assert s.poll() is None
        assert s.state == STATE_BACKOFF
        assert "larger than buffer" in s.last_error
        assert stream.closed

    def test_closed_stream_backs_off(self):
        s, _, stream, _ = _streaming([b""])
        assert s.poll() is None
        assert s.state == STATE_BACKOFF
        assert "closed the stream" in s.last_error
        assert stream.closed

    def test_eagain_oserror_means_nothing_pending(self):
        s, *_ = _streaming([OSError(11), _part(_jpeg(10))])
        assert s.poll() is None
        assert s.state == STATE_STREAMING
        assert bytes(s.poll()) == _jpeg(10)

    def test_counts_frames(self):
        s, *_ = _streaming([_part(_jpeg(10)), None, _part(_jpeg(10))])
        s.poll()
        s.poll()
        assert s.frames == 2

    def test_counts_skipped_parts(self):
        s, *_ = _streaming([_part(_jpeg(10)) + _part(_jpeg(10)) + _part(_jpeg(10))])
        s.poll()
        assert (s.frames, s.parts) == (1, 3)
