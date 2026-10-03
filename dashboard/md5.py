# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  Torgny Bjers

"""
Pure-Python MD5 (RFC 1321), for HTTP Digest auth against the cameras
(dashboard/mjpeg.py). The Presto firmware's hashlib only has sha1/sha256
(confirmed on hardware), and Dahua cameras only offer Digest with
algorithm=MD5. Speed is irrelevant: it hashes three short strings once per
stream connection.

Runs unchanged on CPython and MicroPython (tests/test_md5.py checks it
against hashlib.md5). The 64 round constants are one packed hex string, not
64 int literals -- see CLAUDE.md's note on MicroPython's compiler and many
small literals.
"""

import binascii
import struct

_MASK = 0xFFFFFFFF
_SHIFTS = [7, 12, 17, 22] * 4 + [5, 9, 14, 20] * 4 + [4, 11, 16, 23] * 4 + [6, 10, 15, 21] * 4
# floor(abs(sin(i + 1)) * 2**32), precomputed on the host: the Presto's
# MicroPython build uses single-precision floats, so deriving these from
# math.sin at import silently produces wrong constants on-device (confirmed:
# K[0] comes out 3614090496, not 0xd76aa478 == 3614090360).
_K = struct.unpack(">64I", binascii.unhexlify((
    "d76aa478e8c7b756242070dbc1bdceeef57c0faf4787c62aa8304613fd469501"
    "698098d88b44f7afffff5bb1895cd7be6b901122fd987193a679438e49b40821"
    "f61e2562c040b340265e5a51e9b6c7aad62f105d02441453d8a1e681e7d3fbc8"
    "21e1cde6c33707d6f4d50d87455a14eda9e3e905fcefa3f8676f02d98d2a4c8a"
    "fffa39428771f6816d9d6122fde5380ca4beea444bdecfa9f6bb4b60bebfbc70"
    "289b7ec6eaa127fad4ef308504881d05d9d4d039e6db99e51fa27cf8c4ac5665"
    "f4292244432aff97ab9423a7fc93a039655b59c38f0ccc92ffeff47d85845dd1"
    "6fa87e4ffe2ce6e0a30143144e0811a1f7537e82bd3af2352ad7d2bbeb86d391"
)))


def _rotl(x, n):
    return ((x << n) | (x >> (32 - n))) & _MASK


def md5(data):
    """Returns the 16-byte MD5 digest of `data` (bytes or str)."""
    if isinstance(data, str):
        data = data.encode()
    length_bits = (len(data) * 8) & 0xFFFFFFFFFFFFFFFF
    padded = bytearray(data)
    padded.append(0x80)
    while len(padded) % 64 != 56:
        padded.append(0)
    padded += struct.pack("<Q", length_bits)

    a0, b0, c0, d0 = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476
    for offset in range(0, len(padded), 64):
        m = struct.unpack("<16I", padded[offset : offset + 64])
        a, b, c, d = a0, b0, c0, d0
        for i in range(64):
            if i < 16:
                f = (b & c) | (~b & d)
                g = i
            elif i < 32:
                f = (d & b) | (~d & c)
                g = (5 * i + 1) % 16
            elif i < 48:
                f = b ^ c ^ d
                g = (3 * i + 5) % 16
            else:
                f = c ^ (b | (~d & _MASK))
                g = (7 * i) % 16
            f = (f + a + _K[i] + m[g]) & _MASK
            a, d, c = d, c, b
            b = (b + _rotl(f, _SHIFTS[i])) & _MASK
        a0 = (a0 + a) & _MASK
        b0 = (b0 + b) & _MASK
        c0 = (c0 + c) & _MASK
        d0 = (d0 + d) & _MASK
    return struct.pack("<4I", a0, b0, c0, d0)


def md5_hex(data):
    return "".join("{:02x}".format(byte) for byte in md5(data))
