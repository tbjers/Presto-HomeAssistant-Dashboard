"""
Minimal America/New_York DST calculation.

tmos.OS.utc_offset (see tmos.py's OS.localtime()) is a static hour offset
with no DST awareness of its own, and MicroPython has no zoneinfo/tzdata.
eastern_utc_offset() computes what that offset should currently be; it's
meant to be re-evaluated periodically by a task (see DashboardApp.tasks())
so a device left running across a DST transition picks up the change
without a reboot.
"""

import time

_STD_OFFSET = -5  # EST
_DST_OFFSET = -4  # EDT

_MONTH_TABLE = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)


def _weekday(year, month, day):
    """0=Monday..6=Sunday, matching time.gmtime()'s weekday field."""
    y = year - 1 if month < 3 else year
    dow_sunday_zero = (y + y // 4 - y // 100 + y // 400 + _MONTH_TABLE[month - 1] + day) % 7
    return (dow_sunday_zero + 6) % 7


def _nth_sunday(year, month, n):
    day = 1
    while _weekday(year, month, day) != 6:
        day += 1
    return day + (n - 1) * 7


def eastern_utc_offset(utc_time=None):
    """
    Returns the current America/New_York UTC offset in whole hours: -4
    while DST is in effect, -5 otherwise.

    :param utc_time: A UTC time.struct_time-like tuple/sequence (as
      returned by time.gmtime()), indexable as
      (year, month, mday, hour, minute, ...). Defaults to time.gmtime().

    US DST runs from 2am local on the 2nd Sunday of March to 2am local
    on the 1st Sunday of November -- approximated here as 07:00 UTC
    (still EST at that instant) through 06:00 UTC (still EDT), which is
    exact for the US rule.
    """
    t = utc_time if utc_time is not None else time.gmtime()
    year, month, mday, hour, minute = t[0], t[1], t[2], t[3], t[4]

    dst_start = (3, _nth_sunday(year, 3, 2), 7, 0)
    dst_end = (11, _nth_sunday(year, 11, 1), 6, 0)
    now = (month, mday, hour, minute)

    return _DST_OFFSET if dst_start <= now < dst_end else _STD_OFFSET
