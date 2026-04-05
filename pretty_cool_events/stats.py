"""Thread-safe statistics tracking with SSE event broadcasting."""

from __future__ import annotations

import json
import queue
import threading
from typing import Any


class StatsTracker:
    """Tracks event processing statistics with thread safety and live event streaming."""

    def __init__(self, timeline_max: int = 1000) -> None:
        self._lock = threading.Lock()
        self._events_received: int = 0
        self._events_matched: int = 0
        self._plugin_stats: dict[str, int] = {}
        self._event_stats: dict[str, int] = {}
        self._event_timeline: list[dict[str, str]] = []
        self._timeline_max = timeline_max
        self._sse_subscribers: list[queue.Queue[str]] = []
        self._sse_lock = threading.Lock()

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

    def publish_event(self, event: dict[str, Any]) -> None:
        """Broadcast a live event to all SSE subscribers."""
        data = json.dumps(event, default=str)
        with self._sse_lock:
            dead: list[queue.Queue[str]] = []
            for q in self._sse_subscribers:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._sse_subscribers.remove(q)

    def publish_stats(self) -> None:
        """Broadcast current stats snapshot to all SSE subscribers."""
        snap = self.snapshot()
        data = json.dumps({"type": "stats", **snap}, default=str)
        with self._sse_lock:
            dead: list[queue.Queue[str]] = []
            for q in self._sse_subscribers:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._sse_subscribers.remove(q)

    def subscribe(self) -> queue.Queue[str]:
        """Create a new SSE subscriber queue."""
        q: queue.Queue[str] = queue.Queue(maxsize=100)
        with self._sse_lock:
            self._sse_subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[str]) -> None:
        """Remove an SSE subscriber."""
        with self._sse_lock:
            if q in self._sse_subscribers:
                self._sse_subscribers.remove(q)

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
