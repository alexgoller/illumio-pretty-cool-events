"""Tests for the StatsTracker."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from pretty_cool_events.stats import StatsTracker


class TestStatsTracker:
    def test_record_event(self, stats_tracker: StatsTracker) -> None:
        stats_tracker.record_event("user.login")
        stats_tracker.record_event("user.login")
        stats_tracker.record_event("agent.activate")
        assert stats_tracker.events_received == 3

    def test_record_match(self, stats_tracker: StatsTracker) -> None:
        stats_tracker.record_match("user.login", "PCEStdout")
        stats_tracker.record_match("user.login", "PCEStdout")
        stats_tracker.record_match("user.login", "PCESlack")
        assert stats_tracker.events_matched == 3
        snap = stats_tracker.snapshot()
        assert snap["plugin_stats"]["PCEStdout"] == 2
        assert snap["plugin_stats"]["PCESlack"] == 1

    def test_timeline_cap(self) -> None:
        tracker = StatsTracker(timeline_max=1000)
        for i in range(1200):
            tracker.record_timeline(f"2024-01-01T00:00:{i:04d}Z", "user.login")
        snap = tracker.snapshot()
        assert len(snap["event_timeline"]) == 1000

    def test_snapshot(self, stats_tracker: StatsTracker) -> None:
        stats_tracker.record_event("user.login")
        stats_tracker.record_match("user.login", "PCEStdout")
        stats_tracker.record_timeline("2024-01-01T00:00:00Z", "user.login")

        snap = stats_tracker.snapshot()
        assert "events_received" in snap
        assert "events_matched" in snap
        assert "plugin_stats" in snap
        assert "event_stats" in snap
        assert "event_timeline" in snap
        assert snap["events_received"] == 1
        assert snap["events_matched"] == 1

    def test_thread_safety(self) -> None:
        tracker = StatsTracker()
        num_threads = 10
        events_per_thread = 100

        def worker() -> None:
            for _ in range(events_per_thread):
                tracker.record_event("user.login")

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            for f in futures:
                f.result()

        assert tracker.events_received == num_threads * events_per_thread
