"""Service manager: coordinates event loop, traffic watchers, and plugins.

Supports hot-reloading config without process restart.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from pretty_cool_events.config import AppConfig, load_config
from pretty_cool_events.event_loop import EventLoop, TrafficWatcherLoop
from pretty_cool_events.pce_client import PCEClient
from pretty_cool_events.plugins.base import create_plugins
from pretty_cool_events.stats import StatsTracker
from pretty_cool_events.throttle import Throttler
from pretty_cool_events.watcher import WatcherRegistry

logger = logging.getLogger(__name__)


class ServiceManager:
    """Manages the lifecycle of event loop, traffic watchers, and plugins.

    Supports reload() to pick up config changes without restarting the process.
    """

    def __init__(self, config: AppConfig, stats: StatsTracker) -> None:
        self.config = config
        self.stats = stats
        self.pce_client: PCEClient | None = None
        self.plugins: dict[str, Any] = {}
        self.throttler: Throttler | None = None
        self._event_loop: EventLoop | None = None
        self._traffic_loop: TrafficWatcherLoop | None = None
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start all services based on current config."""
        with self._lock:
            self._start_services()

    def _start_services(self) -> None:
        has_pce = bool(
            self.config.pce.pce
            and self.config.pce.pce_api_user
            and self.config.pce.pce_api_secret
        )

        if not has_pce:
            logger.info("PCE not configured, skipping event loop")
            return

        self.pce_client = PCEClient(
            base_url=self.config.pce.pce_url,
            api_user=self.config.pce.pce_api_user,
            api_secret=self.config.pce.pce_api_secret,
            org_id=self.config.pce.pce_org,
            verify_tls=self.config.pce.verify_tls,
            timeout=float(self.config.pce.pce_timeout),
        )

        if not self.pce_client.health_check():
            logger.warning("PCE health check failed, continuing anyway")

        self.plugins = create_plugins(self.config)
        watcher_registry = WatcherRegistry(self.config.watchers)
        self._event_loop = EventLoop(
            self.pce_client, watcher_registry, self.stats, self.plugins, self.config,
        )
        self.throttler = self._event_loop.throttler

        t = threading.Thread(target=self._event_loop.run, name="event-loop", daemon=True)
        t.start()
        self._threads.append(t)
        logger.info("Event loop started")

        if self.config.traffic_watchers:
            self._traffic_loop = TrafficWatcherLoop(
                self.pce_client, self.config, self.stats, self.plugins,
            )
            t2 = threading.Thread(target=self._traffic_loop.run, name="traffic-watchers", daemon=True)
            t2.start()
            self._threads.append(t2)
            logger.info("Traffic watcher loop started (%d watchers)", len(self.config.traffic_watchers))

    def stop(self) -> None:
        """Stop all running services."""
        with self._lock:
            if self._event_loop:
                self._event_loop.stop()
            if self._traffic_loop:
                self._traffic_loop.stop()
            for t in self._threads:
                t.join(timeout=5)
            self._threads.clear()
            self._event_loop = None
            self._traffic_loop = None
            logger.info("All services stopped")

    def reload(self) -> str:
        """Reload config and restart services. Returns status message."""
        with self._lock:
            config_path = self.config.config_path
            if not config_path:
                return "No config path - cannot reload"

            try:
                new_config = load_config(config_path)
            except Exception as e:
                return f"Config reload failed: {e}"

            # Stop current services (without the outer lock since we hold it)
            if self._event_loop:
                self._event_loop.stop()
            if self._traffic_loop:
                self._traffic_loop.stop()
            for t in self._threads:
                t.join(timeout=5)
            self._threads.clear()
            self._event_loop = None
            self._traffic_loop = None

            # Update config
            self.config.__dict__.update(new_config.__dict__)
            self.config.config_path = config_path

            # Restart
            self._start_services()

            plugin_count = len(self.plugins)
            watcher_count = sum(len(v) for v in self.config.watchers.values())
            traffic_count = len(self.config.traffic_watchers)
            return (
                f"Reloaded: {plugin_count} plugins, {watcher_count} watchers, "
                f"{traffic_count} traffic watchers"
            )

    @property
    def is_running(self) -> bool:
        return self._event_loop is not None and self._event_loop.is_running
