"""
Tests for dashboard.tz.eastern_utc_offset -- verifies the manual US DST
rule (2nd Sunday of March through 1st Sunday of November) against known
transition dates, without relying on a real tzdata/zoneinfo (unavailable
under MicroPython).
"""

from dashboard.tz import eastern_utc_offset


def _utc(year, month, mday, hour, minute=0):
    return (year, month, mday, hour, minute, 0, 0, 0)


class TestEasternUtcOffset:
    def test_mid_winter_is_standard_time(self):
        assert eastern_utc_offset(_utc(2026, 1, 15, 12)) == -5

    def test_mid_summer_is_daylight_time(self):
        assert eastern_utc_offset(_utc(2026, 7, 25, 12)) == -4

    def test_just_before_spring_transition_is_standard_time(self):
        # 2026's 2nd Sunday of March is the 8th; 06:59 UTC is 1:59am EST.
        assert eastern_utc_offset(_utc(2026, 3, 8, 6, 59)) == -5

    def test_at_spring_transition_is_daylight_time(self):
        # 07:00 UTC on that day is 2:00am EST -> clocks jump to 3:00am EDT.
        assert eastern_utc_offset(_utc(2026, 3, 8, 7, 0)) == -4

    def test_just_before_autumn_transition_is_daylight_time(self):
        # 2026's 1st Sunday of November is the 1st; 05:59 UTC is 1:59am EDT.
        assert eastern_utc_offset(_utc(2026, 11, 1, 5, 59)) == -4

    def test_at_autumn_transition_is_standard_time(self):
        # 06:00 UTC on that day is 2:00am EDT -> clocks fall back to 1:00am EST.
        assert eastern_utc_offset(_utc(2026, 11, 1, 6, 0)) == -5

    def test_defaults_to_current_time_when_unspecified(self):
        # Just checking it doesn't blow up and returns a valid offset.
        assert eastern_utc_offset() in (-4, -5)
