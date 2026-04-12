"""Event deduplication and grouping."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class EventGrouper:
    """Deduplicates events by href and groups repeated event types into summaries.

    Dedup: Events with the same href seen within dedup_window are skipped.
    Grouping: When group_min or more events of the same type arrive in one
    batch, they are collapsed into a single summary event.
    """

    def __init__(
        self,
        dedup_window: int = 300,
        group_min: int = 3,
    ) -> None:
        self._dedup_window = dedup_window
        self._group_min = group_min
        self._lock = threading.Lock()
        # href -> timestamp of when we last saw it
        self._seen: dict[str, float] = {}
        self._deduped_count: int = 0

    def process(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Deduplicate and group a batch of events."""
        deduped = self._dedup(events)
        grouped = self._group(deduped)
        return grouped

    def _dedup(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove duplicate events by href."""
        now = time.monotonic()
        result: list[dict[str, Any]] = []

        with self._lock:
            # Prune expired entries
            expired = [k for k, ts in self._seen.items() if now - ts > self._dedup_window]
            for k in expired:
                del self._seen[k]

            for event in events:
                href = event.get("href", "")
                if not href:
                    result.append(event)
                    continue

                if href in self._seen:
                    self._deduped_count += 1
                    logger.debug("Dedup: skipping %s (%s)", href, event.get("event_type"))
                    continue

                self._seen[href] = now
                result.append(event)

        if len(events) != len(result):
            logger.info("Dedup: %d events -> %d (removed %d duplicates)",
                        len(events), len(result), len(events) - len(result))

        return result

    def _group(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Group events of the same type if there are group_min or more."""
        if len(events) < self._group_min:
            return events

        # Count by event type
        by_type: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            et = event.get("event_type", "unknown")
            by_type.setdefault(et, []).append(event)

        result: list[dict[str, Any]] = []
        for event_type, group in by_type.items():
            if len(group) >= self._group_min:
                # Create summary event
                summary = self._create_summary(event_type, group)
                result.append(summary)
                logger.info("Grouped %d '%s' events into one summary", len(group), event_type)
            else:
                result.extend(group)

        return result

    def _create_summary(self, event_type: str, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Create a grouped summary event."""
        timestamps = [e.get("timestamp", "") for e in events if e.get("timestamp")]
        first_ts = min(timestamps) if timestamps else ""
        last_ts = max(timestamps) if timestamps else ""

        return {
            "event_type": event_type,
            "status": events[0].get("status"),
            "severity": events[0].get("severity", "info"),
            "timestamp": last_ts,
            "pce_fqdn": events[0].get("pce_fqdn", ""),
            "href": events[0].get("href", ""),
            "created_by": events[0].get("created_by"),
            "action": events[0].get("action"),
            "resource_changes": events[0].get("resource_changes", []),
            "notifications": events[0].get("notifications", []),
            "is_grouped": True,
            "group_count": len(events),
            "group_first_timestamp": first_ts,
            "group_last_timestamp": last_ts,
            "group_sample": events[0],
        }

    @property
    def deduped_count(self) -> int:
        with self._lock:
            return self._deduped_count

    @property
    def cache_size(self) -> int:
        with self._lock:
            return len(self._seen)
