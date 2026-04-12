"""Tests for event deduplication and grouping."""

from __future__ import annotations

from pretty_cool_events.event_grouper import EventGrouper


class TestDedup:
    def test_unique_events_pass_through(self) -> None:
        grouper = EventGrouper(dedup_window=60, group_min=100)
        events = [
            {"href": "/orgs/1/events/aaa", "event_type": "user.login"},
            {"href": "/orgs/1/events/bbb", "event_type": "user.logout"},
        ]
        result = grouper.process(events)
        assert len(result) == 2

    def test_duplicate_removed(self) -> None:
        grouper = EventGrouper(dedup_window=60, group_min=100)
        events = [
            {"href": "/orgs/1/events/aaa", "event_type": "user.login"},
            {"href": "/orgs/1/events/aaa", "event_type": "user.login"},
        ]
        result = grouper.process(events)
        assert len(result) == 1

    def test_dedup_across_batches(self) -> None:
        grouper = EventGrouper(dedup_window=60, group_min=100)
        batch1 = [{"href": "/orgs/1/events/aaa", "event_type": "user.login"}]
        batch2 = [{"href": "/orgs/1/events/aaa", "event_type": "user.login"}]
        grouper.process(batch1)
        result = grouper.process(batch2)
        assert len(result) == 0
        assert grouper.deduped_count == 1

    def test_no_href_not_deduped(self) -> None:
        grouper = EventGrouper(dedup_window=60, group_min=100)
        events = [
            {"event_type": "user.login"},
            {"event_type": "user.login"},
        ]
        result = grouper.process(events)
        assert len(result) == 2


class TestGrouping:
    def test_group_min_threshold(self) -> None:
        grouper = EventGrouper(dedup_window=60, group_min=3)
        events = [
            {"href": f"/e/{i}", "event_type": "user.login", "timestamp": f"2026-01-01T00:0{i}:00Z", "status": "success", "severity": "info", "pce_fqdn": "test"}
            for i in range(5)
        ]
        result = grouper.process(events)
        assert len(result) == 1
        assert result[0]["is_grouped"] is True
        assert result[0]["group_count"] == 5

    def test_below_threshold_not_grouped(self) -> None:
        grouper = EventGrouper(dedup_window=60, group_min=5)
        events = [
            {"href": f"/e/{i}", "event_type": "user.login", "timestamp": "2026-01-01T00:00:00Z", "status": "success"}
            for i in range(3)
        ]
        result = grouper.process(events)
        assert len(result) == 3
        assert all("is_grouped" not in e for e in result)

    def test_mixed_types_grouped_separately(self) -> None:
        grouper = EventGrouper(dedup_window=60, group_min=2)
        events = [
            {"href": "/e/1", "event_type": "user.login", "timestamp": "t1", "status": "s", "severity": "i", "pce_fqdn": "p"},
            {"href": "/e/2", "event_type": "user.login", "timestamp": "t2", "status": "s", "severity": "i", "pce_fqdn": "p"},
            {"href": "/e/3", "event_type": "user.logout", "timestamp": "t3", "status": "s", "severity": "i", "pce_fqdn": "p"},
            {"href": "/e/4", "event_type": "user.logout", "timestamp": "t4", "status": "s", "severity": "i", "pce_fqdn": "p"},
        ]
        result = grouper.process(events)
        assert len(result) == 2
        types = {r["event_type"] for r in result}
        assert types == {"user.login", "user.logout"}
        assert all(r["is_grouped"] for r in result)

    def test_summary_has_timestamps(self) -> None:
        grouper = EventGrouper(dedup_window=60, group_min=2)
        events = [
            {"href": "/e/1", "event_type": "x", "timestamp": "2026-01-01T00:01:00Z", "status": "s", "severity": "i", "pce_fqdn": "p"},
            {"href": "/e/2", "event_type": "x", "timestamp": "2026-01-01T00:05:00Z", "status": "s", "severity": "i", "pce_fqdn": "p"},
        ]
        result = grouper.process(events)
        assert result[0]["group_first_timestamp"] == "2026-01-01T00:01:00Z"
        assert result[0]["group_last_timestamp"] == "2026-01-01T00:05:00Z"

    def test_cache_size(self) -> None:
        grouper = EventGrouper()
        grouper.process([{"href": f"/e/{i}", "event_type": "t"} for i in range(10)])
        assert grouper.cache_size == 10
