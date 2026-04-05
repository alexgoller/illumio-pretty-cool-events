"""Integration test for the full event processing pipeline."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from pretty_cool_events.config import load_config
from pretty_cool_events.event_loop import EventLoop
from pretty_cool_events.stats import StatsTracker
from pretty_cool_events.watcher import WatcherRegistry
from tests.conftest import MINIMAL_CONFIG_YAML


class TestFullPipeline:
    def test_end_to_end(self, tmp_path: Path) -> None:
        """Create config, mock PCE, run event loop briefly, verify stats."""
        # Write config
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(MINIMAL_CONFIG_YAML, default_flow_style=False))
        config = load_config(config_file)

        # Create components
        stats = StatsTracker()
        watcher_registry = WatcherRegistry(config.watchers)

        # Mock PCE client
        mock_pce = MagicMock()
        sample_events = [
            {
                "event_type": "user.login",
                "status": "success",
                "timestamp": "2024-01-01T00:00:00Z",
                "href": "/orgs/1/events/1",
                "created_by": {"user": {"username": "admin"}},
            },
            {
                "event_type": "user.login",
                "status": "success",
                "timestamp": "2024-01-01T00:00:01Z",
                "href": "/orgs/1/events/2",
                "created_by": {"user": {"username": "operator"}},
            },
            {
                "event_type": "agent.activate",
                "status": "success",
                "timestamp": "2024-01-01T00:00:02Z",
                "href": "/orgs/1/events/3",
                "created_by": {"user": {"username": "system"}},
            },
        ]
        # Return events on first call, then empty
        mock_pce.get_events.side_effect = [sample_events, []]

        # Mock plugin
        mock_plugin = MagicMock()
        plugins = {"PCEStdout": mock_plugin}

        # Create and run event loop
        loop = EventLoop(mock_pce, watcher_registry, stats, plugins, config)

        thread = threading.Thread(target=loop.run, daemon=True)
        thread.start()

        # Let it run for a brief time (enough for one poll cycle)
        time.sleep(0.5)
        loop.stop()
        thread.join(timeout=5.0)

        assert not thread.is_alive()

        # Verify stats
        assert stats.events_received == 3  # All three events recorded
        assert stats.events_matched == 2  # Only the two user.login events matched
        assert mock_plugin.send.call_count == 2

        snap = stats.snapshot()
        assert snap["event_stats"]["user.login"] == 2
        assert snap["event_stats"]["agent.activate"] == 1
        assert snap["plugin_stats"]["PCEStdout"] == 2
