# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
MJPEGStream -- reads a camera's multipart/x-mixed-replace MJPEG stream
straight off the camera (Dahua: /cgi-bin/mjpg/video.cgi?channel=1&subtype=1)
without blocking TmOS's single cooperative run loop. This is the one place
the device talks to anything other than the MQTT broker; see
dashboard/camera_page.py.

Driven by poll(), called from CameraPage.tick():

  * Connecting is split across ticks, one bounded step per call, so no
    single tick blocks for more than ~2x CONNECT_TIMEOUT_S (the WDT is
    ~8s): first an unauthenticated GET to collect the Digest challenge
    (Dahua answers 401 with `Connection: close`), then a fresh connection
    with the Authorization header. Every (re)connect fetches a fresh
    challenge -- nonces expire.
  * Once streaming, the socket is non-blocking: each poll() drains what has
    arrived into one preallocated bytearray (no per-chunk allocation),
    parses complete parts by their Content-Length header (falling back to
    the boundary marker if a camera omits it -- never by scanning for JPEG
    SOI/EOI bytes, which an embedded EXIF thumbnail also contains), and
    returns a memoryview of only the *newest* complete frame. Older
    complete frames in the same read are skipped, so a slow tick can't
    build a backlog. The view is valid until the next poll().
  * Any failure closes the socket and schedules a retry with backoff across
    later polls -- never a sleep loop. `last_error` says why, for the page
    to show and report.

Credentials are passed in from the on-device secrets.py, never from the
MQTT config.
"""

import random
import socket
import time

from dashboard.md5 import md5_hex

CONNECT_TIMEOUT_S = 2
MIN_BACKOFF_MS = 2000
MAX_BACKOFF_MS = 30000
# Holds at least one whole part (headers + JPEG). A D1 MJPEG frame from a
# Dahua substream is ~30-60KB; 256KB leaves room for a busy scene at high
# quality plus the start of the next part. PSRAM heap is ~8MB.
BUFFER_SIZE = 256 * 1024
# Upper bound on bytes drained per poll(), so one tick can't spin forever
# on a fast stream; at 1 fps D1 a tick sees a few KB.
MAX_READ_PER_POLL = 128 * 1024
MAX_HEADER_BYTES = 4096

STATE_IDLE = "idle"
STATE_CHALLENGE = "challenge"
STATE_AUTH = "auth"
STATE_STREAMING = "streaming"
STATE_BACKOFF = "backoff"


class StreamError(Exception):
    pass


def parse_url(url):
    """http://host[:port]/path?query -> (host, port, path_with_query)."""
    if not url.startswith("http://"):
        raise ValueError("only http:// stream URLs are supported")
    rest = url[len("http://") :]
    slash = rest.find("/")
    if slash == -1:
        hostport, path = rest, "/"
    else:
        hostport, path = rest[:slash], rest[slash:]
    if ":" in hostport:
        host, port = hostport.split(":", 1)
        port = int(port)
    else:
        host, port = hostport, 80
    return host, port, path


def parse_challenge(header_value):
    """Parses a `WWW-Authenticate: Digest k="v", k2=v2` value into a dict
    with lowercase keys. Returns None if it isn't a Digest challenge."""
    value = header_value.strip()
    if not value.lower().startswith("digest "):
        return None
    params = {}
    rest = value[7:]
    i = 0
    n = len(rest)
    while i < n:
        while i < n and rest[i] in " ,":
            i += 1
        eq = rest.find("=", i)
        if eq == -1:
            break
        key = rest[i:eq].strip().lower()
        i = eq + 1
        if i < n and rest[i] == '"':
            end = rest.find('"', i + 1)
            if end == -1:
                end = n
            params[key] = rest[i + 1 : end]
            i = end + 1
        else:
            end = rest.find(",", i)
            if end == -1:
                end = n
            params[key] = rest[i:end].strip()
            i = end
    return params


def digest_authorization(user, password, method, uri, challenge, cnonce, nc=1):
    """Builds an RFC 2617 `Authorization: Digest ...` header value for an
    MD5 challenge, with qop=auth when the server offers it."""
    realm = challenge.get("realm", "")
    nonce = challenge.get("nonce", "")
    ha1 = md5_hex("{}:{}:{}".format(user, realm, password))
    ha2 = md5_hex("{}:{}".format(method, uri))
    qops = [q.strip() for q in challenge.get("qop", "").split(",") if q.strip()]
    nc_value = "{:08x}".format(nc)
    if "auth" in qops:
        response = md5_hex("{}:{}:{}:{}:auth:{}".format(ha1, nonce, nc_value, cnonce, ha2))
    else:
        response = md5_hex("{}:{}:{}".format(ha1, nonce, ha2))
    parts = [
        'username="{}"'.format(user),
        'realm="{}"'.format(realm),
        'nonce="{}"'.format(nonce),
        'uri="{}"'.format(uri),
        'response="{}"'.format(response),
    ]
    if "auth" in qops:
        parts += ["qop=auth", "nc={}".format(nc_value), 'cnonce="{}"'.format(cnonce)]
    if "opaque" in challenge:
        parts.append('opaque="{}"'.format(challenge["opaque"]))
    if "algorithm" in challenge:
        parts.append("algorithm={}".format(challenge["algorithm"]))
    return "Digest " + ", ".join(parts)


def parse_headers(raw):
    """Parses an HTTP header block (bytes, without the blank line) into
    (first_line, {lowercase-name: value})."""
    lines = bytes(raw).decode().split("\r\n")
    headers = {}
    for line in lines[1:]:
        colon = line.find(":")
        if colon > 0:
            headers[line[:colon].strip().lower()] = line[colon + 1 :].strip()
    return lines[0], headers


def _status_code(first_line):
    parts = first_line.split(" ")
    if len(parts) < 2 or not parts[0].startswith("HTTP/"):
        raise StreamError("bad status line: " + first_line[:40])
    return int(parts[1])


def _boundary(content_type):
    for param in content_type.split(";"):
        param = param.strip()
        if param.lower().startswith("boundary="):
            value = param[9:].strip().strip('"')
            if value.startswith("--"):
                value = value[2:]
            return value
    return None


def default_connect(host, port):
    sock = socket.socket()
    sock.settimeout(CONNECT_TIMEOUT_S)
    sock.connect(socket.getaddrinfo(host, port)[0][-1])
    return sock


class MJPEGStream:
    def __init__(self, url, user, password, connect=default_connect, buffer_size=BUFFER_SIZE):
        self._host, self._port, self._path = parse_url(url)
        self._user = user
        self._password = password
        self._connect = connect
        self._buf = bytearray(buffer_size)
        self._view = memoryview(self._buf)
        self._fill = 0
        self._consumed = 0
        self._sock = None
        self._challenge = None
        self._boundary = None
        self._backoff_ms = MIN_BACKOFF_MS
        self._retry_at = 0
        self.state = STATE_IDLE
        self.last_error = None
        # frames: complete frames returned by poll(); parts: every complete
        # frame parsed. parts - frames = frames skipped because a newer one
        # arrived in the same poll.
        self.frames = 0
        self.parts = 0

    # -- lifecycle ----------------------------------------------------------

    def start(self):
        if self.state == STATE_IDLE:
            self._backoff_ms = MIN_BACKOFF_MS
            self.state = STATE_CHALLENGE

    def stop(self):
        self._close()
        self.state = STATE_IDLE

    def poll(self):
        """One bounded step. Returns a memoryview of the newest complete
        JPEG received since the last call, or None. Never raises."""
        try:
            if self.state == STATE_BACKOFF:
                if time.ticks_diff(time.ticks_ms(), self._retry_at) >= 0:
                    self.state = STATE_CHALLENGE
                return None
            if self.state == STATE_CHALLENGE:
                self._fetch_challenge()
                return None
            if self.state == STATE_AUTH:
                self._open_stream()
                return None
            if self.state == STATE_STREAMING:
                return self._read_frames()
        except Exception as exc:  # noqa: BLE001 -- a stream fault must never kill the run loop
            self._fail(exc)
        return None

    # -- connecting ---------------------------------------------------------

    def _request(self, extra_headers=""):
        sock = self._connect(self._host, self._port)
        self._sock = sock
        host = self._host if self._port == 80 else "{}:{}".format(self._host, self._port)
        sock.write(
            "GET {} HTTP/1.1\r\nHost: {}\r\n{}User-Agent: presto\r\n\r\n".format(
                self._path, host, extra_headers
            ).encode()
        )
        # Blocking (bounded by the socket timeout) until the header block
        # is in; any body bytes that arrive with it stay in self._buf.
        self._fill = 0
        self._consumed = 0
        while True:
            end = self._find(b"\r\n\r\n", 0)
            if end != -1:
                break
            if self._fill >= MAX_HEADER_BYTES:
                raise StreamError("response headers too long")
            n = sock.readinto(self._view[self._fill : MAX_HEADER_BYTES])
            if not n:
                raise StreamError("connection closed during headers")
            self._fill += n
        first_line, headers = parse_headers(self._view[:end])
        self._consumed = end + 4
        return _status_code(first_line), headers

    def _fetch_challenge(self):
        status, headers = self._request()
        self._close()
        if status != 401:
            raise StreamError("expected 401 challenge, got {}".format(status))
        challenge = parse_challenge(headers.get("www-authenticate", ""))
        if challenge is None:
            raise StreamError("no Digest challenge")
        self._challenge = challenge
        self.state = STATE_AUTH

    def _open_stream(self):
        cnonce = "{:08x}{:08x}".format(random.getrandbits(32), random.getrandbits(32))
        auth = digest_authorization(
            self._user, self._password, "GET", self._path, self._challenge, cnonce
        )
        status, headers = self._request("Authorization: {}\r\n".format(auth))
        if status == 401:
            raise StreamError("401: camera rejected the credentials")
        if status != 200:
            raise StreamError("stream request failed: HTTP {}".format(status))
        self._boundary = _boundary(headers.get("content-type", ""))
        self._sock.settimeout(0)
        self._backoff_ms = MIN_BACKOFF_MS
        self.last_error = None
        self.state = STATE_STREAMING

    # -- streaming ----------------------------------------------------------

    def _read_frames(self):
        self._compact()
        drained = 0
        while self._fill < len(self._buf) and drained < MAX_READ_PER_POLL:
            try:
                n = self._sock.readinto(self._view[self._fill :])
            except OSError as exc:
                if exc.args and exc.args[0] == 11:  # EAGAIN: nothing pending
                    break
                raise
            if n is None:
                break
            if n == 0:
                raise StreamError("camera closed the stream")
            self._fill += n
            drained += n

        latest = None
        while True:
            part = self._next_part()
            if part is None:
                break
            self.parts += 1
            latest = part
        if latest is None and self._consumed == 0 and self._fill == len(self._buf):
            raise StreamError("frame larger than buffer")
        if latest is None:
            return None
        self.frames += 1
        start, length = latest
        return self._view[start : start + length]

    def _next_part(self):
        """Parses one complete part at self._consumed, advancing past it.
        Returns (start, length) of its body, or None if incomplete."""
        header_end = self._find(b"\r\n\r\n", self._consumed)
        if header_end == -1:
            if self._fill - self._consumed > MAX_HEADER_BYTES:
                raise StreamError("lost multipart sync")
            return None
        if header_end - self._consumed > MAX_HEADER_BYTES:
            raise StreamError("lost multipart sync")
        _, headers = parse_headers(b"x\r\n" + bytes(self._view[self._consumed : header_end]))
        body = header_end + 4
        length = headers.get("content-length")
        if length is not None:
            length = int(length)
            if body + length > self._fill:
                return None
        else:
            if not self._boundary:
                raise StreamError("part has no Content-Length and stream has no boundary")
            marker = self._find(b"\r\n--" + self._boundary.encode(), body)
            if marker == -1:
                return None
            length = marker - body
        self._consumed = body + length
        return body, length

    def _compact(self):
        if self._consumed:
            remaining = self._fill - self._consumed
            self._buf[:remaining] = self._view[self._consumed : self._fill]
            self._fill = remaining
            self._consumed = 0

    def _find(self, needle, start):
        # bytearray.find over only the filled region; slicing a memoryview
        # into bytes would copy up to BUFFER_SIZE per call.
        index = self._buf.find(needle, start, self._fill)
        return index

    # -- failure ------------------------------------------------------------

    def _fail(self, exc):
        self.last_error = "{}: {}".format(type(exc).__name__, exc)
        self._close()
        self.state = STATE_BACKOFF
        self._retry_at = time.ticks_add(time.ticks_ms(), self._backoff_ms)
        self._backoff_ms = min(self._backoff_ms * 2, MAX_BACKOFF_MS)

    def _close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._fill = 0
        self._consumed = 0
