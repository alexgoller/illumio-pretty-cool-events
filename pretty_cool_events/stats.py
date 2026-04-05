"""Thread-safe statistics tracking."""

from __future__ import annotations

import threading
from typing import Any


class StatsTracker:
    """Tracks event processing statistics with thread safety."""

    def __init__(self, timeline_max: int = 1000) -> None:
        self._lock = threading.Lock()
        self._events_received: int = 0
        self._events_matched: int = 0
        self._plugin_stats: dict[str, int] = {}
        self._event_stats: dict[str, int] = {}
        self._event_timeline: list[dict[str, str]] = []
        self._timeline_max = timeline_max

    def record_event(self, event_type: str) -> None:
        with self._lock:
            self._events_received += 1
            self._event_stats[event_type] = self._event_stats.get(event_type, 0) + 1

    def record_match(self, event_type: str, plugin_name: str) -> None:
        with self._lock:
            self._events_matched += 1
            self._plugin_stats[plugin_name] = self._plugin_stats.get(plugin_name, 0) + 1

    def record_timeline(self, timestamp: str, event_type: str) -> None:
        with self._lock:
            self._event_timeline.append({
                "timestamp": timestamp,
                "event_type": event_type,
            })
            if len(self._event_timeline) > self._timeline_max:
                self._event_timeline = self._event_timeline[-self._timeline_max:]

    @property
    def events_received(self) -> int:
        with self._lock:
            return self._events_received

    @property
    def events_matched(self) -> int:
        with self._lock:
            return self._events_matched

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of all stats for serialization."""
        with self._lock:
            return {
                "events_received": self._events_received,
                "events_matched": self._events_matched,
                "plugin_stats": dict(self._plugin_stats),
                "event_stats": dict(self._event_stats),
                "event_timeline": list(self._event_timeline),
            }
