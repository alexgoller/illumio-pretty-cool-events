"""Event throttling to prevent notification storms.

Tracks event dispatch counts per throttle key (event_type + plugin)
and suppresses events that exceed the configured rate limit.

Throttle format: "N/period" where N is the max count and period is
a duration like "1m", "1h", "24h", "7d".

Examples:
    "1/1h"   = max 1 notification per hour per event_type+plugin
    "5/1h"   = max 5 per hour
    "10/24h" = max 10 per day
    "0/1h"   = suppress all (mute)
    ""       = no throttle (unlimited)
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


def parse_throttle(spec: str) -> tuple[int, float] | None:
    """Parse a throttle spec like '5/1h' into (max_count, window_seconds).

    Returns None if the spec is empty or invalid (meaning no throttle).
    """
    if not spec or not spec.strip():
        return None

    m = re.match(r"^(\d+)/(\d+)([mhdw])$", spec.strip())
    if not m:
        logger.warning("Invalid throttle spec: '%s'", spec)
        return None

    count = int(m.group(1))
    amount = int(m.group(2))
    unit = m.group(3)
    multipliers = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
    window = amount * multipliers[unit]
    return (count, window)


class Throttler:
    """Thread-safe event throttler.

    Tracks dispatch timestamps per key and checks whether a new
    dispatch would exceed the configured rate limit.
    """

    def __init__(self, default_spec: str = "") -> None:
        self._default = parse_throttle(default_spec)
        self._lock = threading.Lock()
        # key -> list of timestamps (epoch seconds)
        self._history: dict[str, list[float]] = {}
        self._suppressed: dict[str, int] = {}

    @property
    def default_spec(self) -> str:
        if self._default is None:
            return ""
        count, window = self._default
        # Reverse-engineer the spec string
        if window >= 604800:
            return f"{count}/{window // 604800}w"
        if window >= 86400:
            return f"{count}/{window // 86400}d"
        if window >= 3600:
            return f"{count}/{window // 3600}h"
        return f"{count}/{window // 60}m"

    def update_default(self, spec: str) -> None:
        """Update the default throttle spec."""
        self._default = parse_throttle(spec)

    def allow(self, event_type: str, plugin: str, override_spec: str = "") -> bool:
        """Check if an event dispatch is allowed under the throttle.

        Args:
            event_type: The PCE event type (e.g. "user.login")
            plugin: The plugin name (e.g. "PCESlack")
            override_spec: Per-watcher throttle override (e.g. "5/1h").
                          Empty string means use the default.

        Returns:
            True if the dispatch is allowed, False if throttled.
        """
        # Determine which throttle to apply
        spec = parse_throttle(override_spec) if override_spec else None
        limit = spec or self._default

        if limit is None:
            return True  # No throttle configured

        max_count, window = limit
        key = f"{event_type}:{plugin}"
        now = time.monotonic()

        with self._lock:
            history = self._history.setdefault(key, [])

            # Prune expired entries
            cutoff = now - window
            history[:] = [t for t in history if t > cutoff]

            if len(history) >= max_count:
                self._suppressed[key] = self._suppressed.get(key, 0) + 1
                return False

            history.append(now)
            return True

    def suppressed_count(self, event_type: str, plugin: str) -> int:
        """Return how many events have been suppressed for this key."""
        key = f"{event_type}:{plugin}"
        with self._lock:
            return self._suppressed.get(key, 0)

    def snapshot(self) -> dict[str, Any]:
        """Return throttle state for monitoring."""
        with self._lock:
            return {
                "default": self.default_spec,
                "active_keys": len(self._history),
                "total_suppressed": sum(self._suppressed.values()),
                "suppressed_by_key": dict(self._suppressed),
            }

    def reset(self) -> None:
        """Clear all throttle state."""
        with self._lock:
            self._history.clear()
            self._suppressed.clear()
