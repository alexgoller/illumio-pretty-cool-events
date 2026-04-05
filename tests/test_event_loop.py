"""Tests for the EventLoop."""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pretty_cool_events.config import AppConfig, WatcherAction
from pretty_cool_events.event_loop import EventLoop
from pretty_cool_events.pce_client import PCEClient
from pretty_cool_events.stats import StatsTracker
from pretty_cool_events.watcher import WatcherRegistry


@pytest.fixture()
def mock_pce_client() -> MagicMock:
    client = MagicMock(spec=PCEClient)
    client.get_events.return_value = []
    return client


@pytest.fixture()
def simple_config(sample_config: AppConfig) -> AppConfig:
    return sample_config


@pytest.fixture()
def watcher_registry(simple_config: AppConfig) -> WatcherRegistry:
    return WatcherRegistry(simple_config.watchers)


@pytest.fixture()
def mock_plugin() -> MagicMock:
    plugin = MagicMock()
    plugin.send = MagicMock()
    return plugin


class TestEventLoop:
    def test_event_routing(
        self,
        mock_pce_client: MagicMock,
        watcher_registry: WatcherRegistry,
        stats_tracker: StatsTracker,
        mock_plugin: MagicMock,
        simple_config: AppConfig,
        sample_event: dict[str, Any],
    ) -> None:
        mock_pce_client.get_events.return_value = [sample_event]
        plugins = {"PCEStdout": mock_plugin}

        loop = EventLoop(mock_pce_client, watcher_registry, stats_tracker, plugins, simple_config)

        # Run one polling cycle directly
        from datetime import datetime, timezone

        loop._poll_events(datetime.now(timezone.utc))

        mock_plugin.send.assert_called_once()
        assert stats_tracker.events_received == 1
        assert stats_tracker.events_matched == 1

    def test_graceful_shutdown(
        self,
        mock_pce_client: MagicMock,
        watcher_registry: WatcherRegistry,
        stats_tracker: StatsTracker,
        simple_config: AppConfig,
    ) -> None:
        loop = EventLoop(
            mock_pce_client, watcher_registry, stats_tracker, {}, simple_config
        )

        thread = threading.Thread(target=loop.run, daemon=True)
        thread.start()

        # Give the loop a moment to start, then stop it
        time.sleep(0.1)
        loop.stop()
        thread.join(timeout=3.0)

        assert not thread.is_alive(), "Event loop thread did not exit in time"

    def test_plugin_error_recovery(
        self,
        mock_pce_client: MagicMock,
        watcher_registry: WatcherRegistry,
        stats_tracker: StatsTracker,
        simple_config: AppConfig,
        sample_event: dict[str, Any],
    ) -> None:
        """Plugin that raises should not crash the loop."""
        bad_plugin = MagicMock()
        bad_plugin.send.side_effect = RuntimeError("plugin exploded")
        plugins = {"PCEStdout": bad_plugin}

        # Send two events
        second_event = dict(sample_event)
        mock_pce_client.get_events.return_value = [sample_event, second_event]

        loop = EventLoop(
            mock_pce_client, watcher_registry, stats_tracker, plugins, simple_config
        )

        from datetime import datetime, timezone

        # Should not raise
        loop._poll_events(datetime.now(timezone.utc))

        # Both events should have been received even though the plugin failed
        assert stats_tracker.events_received == 2

    def test_unmatched_events(
        self,
        mock_pce_client: MagicMock,
        watcher_registry: WatcherRegistry,
        stats_tracker: StatsTracker,
        mock_plugin: MagicMock,
        simple_config: AppConfig,
    ) -> None:
        """Events that don't match any watcher are recorded but not routed."""
        unmatched_event = {
            "event_type": "agent.activate",
            "status": "success",
            "timestamp": "2024-01-01T00:00:00Z",
        }
        mock_pce_client.get_events.return_value = [unmatched_event]
        plugins = {"PCEStdout": mock_plugin}

        loop = EventLoop(
            mock_pce_client, watcher_registry, stats_tracker, plugins, simple_config
        )

        from datetime import datetime, timezone

        loop._poll_events(datetime.now(timezone.utc))

        assert stats_tracker.events_received == 1
        assert stats_tracker.events_matched == 0
        mock_plugin.send.assert_not_called()
