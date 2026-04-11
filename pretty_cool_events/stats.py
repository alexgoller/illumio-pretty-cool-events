"""Thread-safe statistics tracking with SSE event broadcasting."""

from __future__ import annotations

import json
import queue
import threading
from datetime import datetime, timezone
from typing import Any


class StatsTracker:
    """Tracks event processing statistics with thread safety and live event streaming."""

    def __init__(self, timeline_max: int = 1000, history_max: int = 500) -> None:
        self._lock = threading.Lock()
        self._events_received: int = 0
        self._events_matched: int = 0
        self._events_dispatched: int = 0
        self._plugin_stats: dict[str, int] = {}
        # Notification history (rolling log of dispatches)
        self._dispatch_history: list[dict[str, Any]] = []
        self._history_max = history_max
        self._event_stats: dict[str, int] = {}
        self._event_timeline: list[dict[str, str]] = []
        self._timeline_max = timeline_max
        self._sse_subscribers: list[queue.Queue[str]] = []
        self._sse_lock = threading.Lock()
        # Traffic watcher stats
        self._traffic_watcher_runs: dict[str, int] = {}  # name -> run count
        self._traffic_watcher_flows: dict[str, int] = {}  # name -> total flows found
        self._traffic_watcher_last_run: dict[str, str] = {}  # name -> ISO timestamp
        # PCE connection status
        self._pce_status: str = "unknown"  # "connected", "error", "unknown"
        self._pce_last_error: str = ""
        self._pce_last_success: str = ""
        self._pce_consecutive_failures: int = 0

    def record_traffic_watcher(self, name: str, flows: int) -> None:
        with self._lock:
            self._traffic_watcher_runs[name] = self._traffic_watcher_runs.get(name, 0) + 1
            self._traffic_watcher_flows[name] = self._traffic_watcher_flows.get(name, 0) + flows
            self._traffic_watcher_last_run[name] = datetime.now(timezone.utc).isoformat()

    def record_pce_success(self) -> None:
        with self._lock:
            self._pce_status = "connected"
            self._pce_last_success = datetime.now(timezone.utc).isoformat()
            self._pce_consecutive_failures = 0
            self._pce_last_error = ""

    def record_pce_error(self, error: str) -> None:
        with self._lock:
            self._pce_status = "error"
            self._pce_last_error = error
            self._pce_consecutive_failures += 1

    def record_event(self, event_type: str) -> None:
        with self._lock:
            self._events_received += 1
            self._event_stats[event_type] = self._event_stats.get(event_type, 0) + 1

    def record_matched_event(self) -> None:
        """Record that an event had at least one watcher match (call once per event)."""
        with self._lock:
            self._events_matched += 1

    def record_dispatch(self, event_type: str, plugin_name: str,
                        success: bool = True, error: str = "") -> None:
        """Record a plugin dispatch with history."""
        with self._lock:
            self._events_dispatched += 1
            self._plugin_stats[plugin_name] = self._plugin_stats.get(plugin_name, 0) + 1
            self._dispatch_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                "plugin": plugin_name,
                "success": success,
                "error": error,
            })
            if len(self._dispatch_history) > self._history_max:
                self._dispatch_history = self._dispatch_history[-self._history_max:]

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
        """Broadcast lightweight stats to SSE subscribers (no large lists)."""
        with self._lock:
            lite = {
                "type": "stats",
                "events_received": self._events_received,
                "events_matched": self._events_matched,
                "events_dispatched": self._events_dispatched,
                "plugin_stats": dict(self._plugin_stats),
                "event_stats": dict(self._event_stats),
                "pce_status": self._pce_status,
                "pce_last_error": self._pce_last_error,
                "pce_last_success": self._pce_last_success,
                "pce_consecutive_failures": self._pce_consecutive_failures,
            }
        data = json.dumps(lite, default=str)
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
                "events_dispatched": self._events_dispatched,
                "plugin_stats": dict(self._plugin_stats),
                "event_stats": dict(self._event_stats),
                "event_timeline": list(self._event_timeline),
                "dispatch_history": list(self._dispatch_history),
                "traffic_watcher_runs": dict(self._traffic_watcher_runs),
                "traffic_watcher_flows": dict(self._traffic_watcher_flows),
                "traffic_watcher_last_run": dict(self._traffic_watcher_last_run),
                "pce_status": self._pce_status,
                "pce_last_error": self._pce_last_error,
                "pce_last_success": self._pce_last_success,
                "pce_consecutive_failures": self._pce_consecutive_failures,
            }
