"""Shared test fixtures for pretty_cool_events."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from pretty_cool_events.config import AppConfig, load_config
from pretty_cool_events.stats import StatsTracker


MINIMAL_CONFIG_YAML = {
    "config": {
        "pce": "pce212-sample.foo.com",
        "pce_api_user": "api_1d9f490a0eabff1c4",
        "pce_api_secret": "secret123",
        "pce_org": 1,
        "pce_poll_interval": 10,
        "httpd": False,
        "default_template": "default.html",
        "plugin_config": {
            "PCEStdout": {
                "prepend": "Pretty cool events: ",
            },
        },
    },
    "watchers": {
        "user.login": [
            {
                "status": "success",
                "plugin": "PCEStdout",
                "extra_data": {"template": "default.html"},
            },
        ],
    },
}


@pytest.fixture()
def sample_config_path(tmp_path: Path) -> Path:
    """Write a minimal valid config YAML to tmp_path and return the path."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG_YAML, default_flow_style=False))
    return config_file


@pytest.fixture()
def sample_config(sample_config_path: Path) -> AppConfig:
    """Return a loaded AppConfig from the sample config file."""
    return load_config(sample_config_path)


@pytest.fixture()
def sample_event() -> dict[str, Any]:
    """Return a realistic sample event dict."""
    return {
        "event_type": "user.login",
        "status": "success",
        "timestamp": "2024-01-01T00:00:00Z",
        "href": "/orgs/1/events/123",
        "created_by": {"user": {"username": "admin"}},
    }


@pytest.fixture()
def stats_tracker() -> StatsTracker:
    """Return a fresh StatsTracker instance."""
    return StatsTracker()
