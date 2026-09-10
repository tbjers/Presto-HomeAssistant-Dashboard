"""
Tests for dashboard.watchdog.WatchdogFeeder.
"""

from dashboard.watchdog import WatchdogFeeder


class TestWatchdogFeeder:
    def test_arms_on_first_tick_not_at_construction(self, mock_machine_module):
        feeder = WatchdogFeeder(8000)
        mock_machine_module.WDT.assert_not_called()

        feeder.tick()

        mock_machine_module.WDT.assert_called_once_with(timeout=8000)

    def test_only_arms_once(self, mock_machine_module):
        feeder = WatchdogFeeder(8000)

        feeder.tick()
        feeder.tick()
        feeder.tick()

        mock_machine_module.WDT.assert_called_once()

    def test_feeds_every_tick(self, mock_machine_module):
        feeder = WatchdogFeeder(8000)
        wdt = mock_machine_module.WDT.return_value

        feeder.tick()
        feeder.tick()
        feeder.tick()

        assert wdt.feed.call_count == 3
