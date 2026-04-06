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

    def test_record_dispatch(self, stats_tracker: StatsTracker) -> None:
        stats_tracker.record_dispatch("user.login", "PCEStdout")
        stats_tracker.record_dispatch("user.login", "PCEStdout")
        stats_tracker.record_dispatch("user.login", "PCESlack")
        snap = stats_tracker.snapshot()
        assert snap["events_dispatched"] == 3
        assert snap["plugin_stats"]["PCEStdout"] == 2
        assert snap["plugin_stats"]["PCESlack"] == 1

    def test_matched_vs_dispatched(self, stats_tracker: StatsTracker) -> None:
        """events_matched counts unique events, dispatched counts per-plugin sends."""
        # One event matched by 2 watchers
        stats_tracker.record_event("user.login")
        stats_tracker.record_matched_event()
        stats_tracker.record_dispatch("user.login", "PCEStdout")
        stats_tracker.record_dispatch("user.login", "PCESlack")

        snap = stats_tracker.snapshot()
        assert snap["events_received"] == 1
        assert snap["events_matched"] == 1   # 1 unique event
        assert snap["events_dispatched"] == 2  # 2 plugin sends

    def test_timeline_cap(self) -> None:
        tracker = StatsTracker(timeline_max=1000)
        for i in range(1200):
            tracker.record_timeline(f"2024-01-01T00:00:{i:04d}Z", "user.login")
        snap = tracker.snapshot()
        assert len(snap["event_timeline"]) == 1000

    def test_snapshot(self, stats_tracker: StatsTracker) -> None:
        stats_tracker.record_event("user.login")
        stats_tracker.record_matched_event()
        stats_tracker.record_dispatch("user.login", "PCEStdout")
        stats_tracker.record_timeline("2024-01-01T00:00:00Z", "user.login")

        snap = stats_tracker.snapshot()
        assert snap["events_received"] == 1
        assert snap["events_matched"] == 1
        assert snap["events_dispatched"] == 1
        assert "plugin_stats" in snap

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
