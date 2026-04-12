"""Tests for the EventLoop."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

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


def _make_loop(
    pce: MagicMock, registry: WatcherRegistry, stats: StatsTracker,
    plugins: dict[str, Any], config: AppConfig,
) -> EventLoop:
    loop = EventLoop(pce, registry, stats, plugins, config)
    loop._watermark = datetime.now(timezone.utc).astimezone()
    return loop


class TestEventLoop:
    def test_event_routing(
        self, mock_pce_client: MagicMock, watcher_registry: WatcherRegistry,
        stats_tracker: StatsTracker, mock_plugin: MagicMock,
        simple_config: AppConfig, sample_event: dict[str, Any],
    ) -> None:
        mock_pce_client.get_events.return_value = [sample_event]
        plugins = {"PCEStdout": mock_plugin}
        loop = _make_loop(mock_pce_client, watcher_registry, stats_tracker, plugins, simple_config)

        loop._poll_events()

        mock_plugin.send.assert_called_once()
        assert stats_tracker.events_received == 1
        assert stats_tracker.events_matched == 1

    def test_graceful_shutdown(
        self, mock_pce_client: MagicMock, watcher_registry: WatcherRegistry,
        stats_tracker: StatsTracker, simple_config: AppConfig,
    ) -> None:
        loop = EventLoop(mock_pce_client, watcher_registry, stats_tracker, {}, simple_config)

        thread = threading.Thread(target=loop.run, daemon=True)
        thread.start()

        time.sleep(0.1)
        loop.stop()
        thread.join(timeout=3.0)

        assert not thread.is_alive(), "Event loop thread did not exit in time"

    def test_plugin_error_recovery(
        self, mock_pce_client: MagicMock, watcher_registry: WatcherRegistry,
        stats_tracker: StatsTracker, simple_config: AppConfig,
        sample_event: dict[str, Any],
    ) -> None:
        """Plugin that raises should not crash the loop."""
        bad_plugin = MagicMock()
        bad_plugin.send.side_effect = RuntimeError("plugin exploded")
        plugins = {"PCEStdout": bad_plugin}

        second_event = dict(sample_event)
        second_event["href"] = "/orgs/1/events/second-event"
        mock_pce_client.get_events.return_value = [sample_event, second_event]

        loop = _make_loop(mock_pce_client, watcher_registry, stats_tracker, plugins, simple_config)
        loop._poll_events()  # Should not raise

        assert stats_tracker.events_received == 2

    def test_unmatched_events(
        self, mock_pce_client: MagicMock, watcher_registry: WatcherRegistry,
        stats_tracker: StatsTracker, mock_plugin: MagicMock,
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

        loop = _make_loop(mock_pce_client, watcher_registry, stats_tracker, plugins, simple_config)
        loop._poll_events()

        assert stats_tracker.events_received == 1
        assert stats_tracker.events_matched == 0
        mock_plugin.send.assert_not_called()

    def test_watermark_advances_on_success(
        self, mock_pce_client: MagicMock, watcher_registry: WatcherRegistry,
        stats_tracker: StatsTracker, simple_config: AppConfig,
    ) -> None:
        """Watermark should advance to latest event timestamp after successful poll."""
        mock_pce_client.get_events.return_value = [
            {"event_type": "user.login", "status": "success", "timestamp": "2026-04-05T10:00:00Z"},
            {"event_type": "user.logout", "status": "success", "timestamp": "2026-04-05T12:00:00Z"},
        ]
        loop = _make_loop(mock_pce_client, watcher_registry, stats_tracker, {}, simple_config)
        # Set watermark to before the events
        loop._watermark = datetime(2026, 4, 5, 8, 0, 0, tzinfo=timezone.utc)

        loop._poll_events()

        # Watermark should advance to the latest event timestamp
        assert loop._watermark.hour == 12  # 12:00:00Z from the second event

    def test_watermark_stays_on_error(
        self, mock_pce_client: MagicMock, watcher_registry: WatcherRegistry,
        stats_tracker: StatsTracker, simple_config: AppConfig,
    ) -> None:
        """Watermark should NOT advance when the PCE poll fails."""
        import httpx

        mock_pce_client.get_events.side_effect = httpx.ConnectError("refused")

        loop = _make_loop(mock_pce_client, watcher_registry, stats_tracker, {}, simple_config)
        old_watermark = loop._watermark

        # The run() method catches the exception and does NOT advance
        # Simulate one iteration
        try:
            loop._poll_events()
        except httpx.ConnectError:
            pass  # Expected - watermark should not have changed

        assert loop._watermark == old_watermark

    def test_serialized_pce_calls(self) -> None:
        """PCE client lock prevents concurrent requests."""
        from pretty_cool_events.pce_client import PCEClient

        client = PCEClient(
            base_url="https://example.com",
            api_user="test",
            api_secret="test",
        )
        assert hasattr(client, "_lock")
        assert isinstance(client._lock, type(threading.Lock()))
        client.close()
