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
                    logger.info("Routing %s -> %s", event_type, action.plugin)
                    plugin.send(event, extra_data, self._template_globals)
                    self._stats.record_dispatch(event_type, action.plugin, success=True)
                except Exception as exc:
                    self._stats.record_dispatch(event_type, action.plugin,
                                                success=False, error=str(exc))
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


class TrafficWatcherLoop:
    """Executes configured traffic watchers on their individual schedules."""

    def __init__(
        self,
        pce_client: PCEClient,
        config: AppConfig,
        stats: StatsTracker,
        plugins: dict[str, OutputPlugin],
    ) -> None:
        self._pce = pce_client
        self._config = config
        self._stats = stats
        self._plugins = plugins
        self._stop_event = threading.Event()
        # Track last run time per watcher name
        self._last_run: dict[str, datetime] = {}
        self._template_globals = {
            "pce_fqdn": config.pce.pce,
            "pce_org": config.pce.pce_org,
        }

    def run(self) -> None:
        """Check all traffic watchers every 60s and run any that are due."""
        logger.info("Traffic watcher loop started (%d watchers configured)",
                     len(self._config.traffic_watchers))

        while not self._stop_event.is_set():
            for tw in self._config.traffic_watchers:
                if self._stop_event.is_set():
                    break
                try:
                    if self._is_due(tw):
                        self._execute_watcher(tw)
                except Exception:
                    logger.exception("Traffic watcher '%s' failed", tw.name)

            # Check every 60 seconds for due watchers
            self._stop_event.wait(timeout=60)

        logger.info("Traffic watcher loop stopped")

    def _parse_interval(self, interval: str) -> float:
        """Parse interval string like '1h', '6h', '24h' to seconds."""
        import re as _re
        m = _re.match(r"^(\d+)([mhdw])$", interval.strip())
        if not m:
            return 86400  # default 24h
        amount = int(m.group(1))
        unit = m.group(2)
        multipliers = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
        return amount * multipliers[unit]

    def _is_due(self, tw: Any) -> bool:
        """Check if a traffic watcher is due to run."""
        interval_secs = self._parse_interval(tw.interval)
        last = self._last_run.get(tw.name)
        if last is None:
            return True  # Never run, run now
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= interval_secs

    def _execute_watcher(self, tw: Any) -> None:
        """Execute a single traffic watcher: query PCE, check results, notify."""
        from pretty_cool_events.label_resolver import LabelResolver

        now = datetime.now(timezone.utc)
        interval_secs = self._parse_interval(tw.interval)
        since = self._last_run.get(tw.name, now - __import__("datetime").timedelta(seconds=interval_secs))

        logger.info("Running traffic watcher: %s (since %s)", tw.name, since.isoformat())

        # Build the label resolver (reuse labels from PCE)
        resolver = LabelResolver()
        labels = self._pce.get_labels()
        resolver.load(labels)

        # Build the PCE query from the watcher config
        src_include = resolver.parse_expression(tw.src_include)
        src_exclude = resolver.parse_exclude(tw.src_exclude)
        dst_include = resolver.parse_expression(tw.dst_include)
        dst_exclude = resolver.parse_exclude(tw.dst_exclude)
        svc_include = resolver.parse_services(tw.services_include)
        svc_exclude = resolver.parse_services(tw.services_exclude)

        query = {
            "query_name": f"tw_{tw.name}_{now.strftime('%H%M%S')}",
            "start_date": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_date": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "policy_decisions": tw.policy_decisions,
            "max_results": tw.max_results,
            "sources": {"include": src_include or [], "exclude": src_exclude},
            "destinations": {"include": dst_include or [], "exclude": dst_exclude},
            "sources_destinations_query_op": "and",
            "services": {"include": svc_include, "exclude": svc_exclude},
        }

        # Submit async query
        result = self._pce.create_traffic_query(query)
        if not result:
            logger.error("Traffic watcher '%s': failed to create query", tw.name)
            return

        # Poll for completion (max 2 minutes)
        import csv
        import io
        import time

        for _attempt in range(24):
            if self._stop_event.is_set():
                return
            time.sleep(5)
            queries = self._pce.list_traffic_queries()
            # Find our query (most recent with our name prefix)
            our = [q for q in queries if q.get("query_parameters", {}).get("query_name", "").startswith(f"tw_{tw.name}_")]
            if not our:
                continue
            latest = our[-1]
            if latest["status"] == "completed" and latest.get("result"):
                # Download and process results
                csv_text = self._pce.download_traffic_results(latest["result"])
                if csv_text:
                    rows = list(csv.DictReader(io.StringIO(csv_text)))
                    self._stats.record_traffic_watcher(tw.name, len(rows))
                    logger.info("Traffic watcher '%s': %d flows found", tw.name, len(rows))

                    if rows:
                        # Send notification via the configured plugin
                        plugin = self._plugins.get(tw.plugin)
                        if plugin:
                            # Build a traffic-specific summary (not a PCE event)
                            summary = {
                                "event_type": f"traffic_watcher.{tw.name}",
                                "status": "alert",
                                "severity": "warning",
                                "timestamp": now.isoformat(),
                                "pce_fqdn": self._config.pce.pce,
                                "is_traffic_alert": True,
                                "traffic_watcher": tw.name,
                                "flows_count": len(rows),
                                "policy_decisions": tw.policy_decisions,
                                "src_include": tw.src_include,
                                "dst_include": tw.dst_include,
                                "services_include": tw.services_include,
                                "sample_flows": rows[:5],
                            }
                            try:
                                plugin.send(summary, {"template": tw.template}, self._template_globals)
                                logger.info("Traffic watcher '%s': notified %s (%d flows)",
                                           tw.name, tw.plugin, len(rows))
                            except Exception:
                                logger.exception("Traffic watcher '%s': plugin %s failed",
                                                tw.name, tw.plugin)
                break
            elif latest["status"] == "failed":
                logger.error("Traffic watcher '%s': query failed on PCE", tw.name)
                break

        # Mark as run regardless of outcome
        self._last_run[tw.name] = now

    def stop(self) -> None:
        self._stop_event.set()
