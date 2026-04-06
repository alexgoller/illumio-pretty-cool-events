"""Main event polling loop with graceful shutdown."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from pretty_cool_events.config import AppConfig
from pretty_cool_events.pce_client import PCEClient
from pretty_cool_events.plugins.base import OutputPlugin
from pretty_cool_events.stats import StatsTracker
from pretty_cool_events.throttle import Throttler
from pretty_cool_events.watcher import WatcherRegistry

logger = logging.getLogger(__name__)


class EventLoop:
    """Polls the PCE for events and routes them through watchers to plugins."""

    def __init__(
        self,
        pce_client: PCEClient,
        watcher_registry: WatcherRegistry,
        stats: StatsTracker,
        plugins: dict[str, OutputPlugin],
        config: AppConfig,
    ) -> None:
        self._pce = pce_client
        self._watchers = watcher_registry
        self._stats = stats
        self._plugins = plugins
        self._config = config
        self._throttler = Throttler(config.throttle_default)
        self._stop_event = threading.Event()
        self._template_globals = {
            "pce_fqdn": config.pce.pce,
            "pce_org": config.pce.pce_org,
        }

    @property
    def throttler(self) -> Throttler:
        return self._throttler

    def run(self) -> None:
        """Run the event polling loop until stop() is called."""
        poll_interval = self._config.pce.pce_poll_interval
        # Watermark: only advance on successful poll to avoid missing events
        self._watermark = datetime.now(timezone.utc).astimezone()

        logger.info("Event loop started (poll interval: %ds)", poll_interval)

        while not self._stop_event.is_set():
            try:
                self._poll_events()
            except Exception as e:
                # On error, do NOT advance the watermark - re-fetch on next poll
                error_msg = str(e)
                self._stats.record_pce_error(error_msg)
                self._stats.publish_event({
                    "type": "pce_error",
                    "error": error_msg,
                    "consecutive_failures": self._stats.snapshot()["pce_consecutive_failures"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                logger.exception("Error in event polling cycle")

            self._stop_event.wait(timeout=poll_interval)

        logger.info("Event loop stopped")

    def _poll_events(self) -> None:
        """Fetch and process events since the watermark."""
        # Capture the poll start time BEFORE the request
        poll_time = datetime.now(timezone.utc).astimezone()

        events = self._pce.get_events(since=self._watermark)
        self._stats.record_pce_success()

        # Advance watermark to the latest event timestamp (or poll time if no events)
        # This prevents gaps: if events arrived during our request, we'll catch them
        # next poll because the watermark is the newest event's timestamp, not "now".
        if events:
            latest_ts = max(
                (e.get("timestamp", "") for e in events if e.get("timestamp")),
                default="",
            )
            if latest_ts:
                try:
                    self._watermark = datetime.fromisoformat(
                        latest_ts.replace("Z", "+00:00")
                    )
                except ValueError:
                    self._watermark = poll_time
            else:
                self._watermark = poll_time
        else:
            self._watermark = poll_time

        for event in events:
            if "event_type" not in event:
                logger.warning("Malformed event (no event_type): %s", event)
                continue

            event_type = event["event_type"]
            timestamp = event.get("timestamp", datetime.now(timezone.utc).isoformat())

            self._stats.record_event(event_type)
            self._stats.record_timeline(timestamp, event_type)

            # Broadcast live event to SSE subscribers
            self._stats.publish_event({
                "type": "event",
                "event_type": event_type,
                "status": event.get("status"),
                "severity": event.get("severity"),
                "timestamp": timestamp,
                "created_by": event.get("created_by"),
            })

            matches = self._watchers.match(event)

            if matches:
                self._stats.record_matched_event()

            for action, extra_data in matches:
                plugin = self._plugins.get(action.plugin)
                if not plugin:
                    logger.warning("Plugin '%s' not available for event %s",
                                   action.plugin, event_type)
                    continue

                # Check throttle (per-watcher override via extra_data.throttle)
                throttle_override = extra_data.get("throttle", "")
                if not self._throttler.allow(event_type, action.plugin, throttle_override):
                    logger.debug("Throttled %s -> %s", event_type, action.plugin)
                    continue

                try:
                    self._stats.record_dispatch(event_type, action.plugin)
                    logger.info("Routing %s -> %s", event_type, action.plugin)
                    plugin.send(event, extra_data, self._template_globals)
                except Exception:
                    logger.exception("Plugin '%s' failed for event %s",
                                     action.plugin, event_type)

        # Broadcast updated stats after processing batch
        if events:
            self._stats.publish_stats()

    def stop(self) -> None:
        """Signal the event loop to stop."""
        logger.info("Stopping event loop...")
        self._stop_event.set()

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()


class TrafficLoop:
    """Polls PCE for traffic flow data."""

    def __init__(self, pce_client: PCEClient, config: AppConfig) -> None:
        self._pce = pce_client
        self._config = config
        self._stop_event = threading.Event()

    def run(self) -> None:
        interval = self._config.pce.pce_traffic_interval
        logger.info("Traffic loop started (interval: %ds)", interval)

        while not self._stop_event.is_set():
            try:
                now = datetime.now(timezone.utc)
                query: dict[str, Any] = {
                    "start_date": (now - __import__("datetime").timedelta(days=1)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "end_date": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "policy_decisions": ["allowed", "blocked"],
                    "max_results": 10000,
                }
                result = self._pce.get_traffic(query)
                if result:
                    logger.debug("Traffic query returned data")
            except Exception:
                logger.exception("Error in traffic polling cycle")

            self._stop_event.wait(timeout=interval)

        logger.info("Traffic loop stopped")

    def stop(self) -> None:
        self._stop_event.set()
