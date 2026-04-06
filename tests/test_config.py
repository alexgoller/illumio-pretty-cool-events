"""Tests for the configuration loading and validation system."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pretty_cool_events.config import AppConfig, load_config, load_event_types, save_config


class TestLoadConfig:
    def test_load_valid_config(self, sample_config: AppConfig) -> None:
        assert sample_config.pce.pce == "pce212-sample.foo.com"
        assert sample_config.pce.pce_org == 1
        assert sample_config.pce.pce_poll_interval == 10
        assert sample_config.pce.pce_api_user == "api_1d9f490a0eabff1c4"

    def test_load_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_load_empty_file(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")
        with pytest.raises(ValueError, match="empty"):
            load_config(empty_file)

    def test_config_defaults(self, sample_config: AppConfig) -> None:
        assert sample_config.httpd.enabled is False
        assert sample_config.default_template == "default.html"
        assert sample_config.traffic_watchers == []

    def test_env_override(self, sample_config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PCE_EVENTS_PCE", "override-pce.example.com")
        config = load_config(sample_config_path)
        assert config.pce.pce == "override-pce.example.com"

    def test_get_active_plugins(self, sample_config: AppConfig) -> None:
        plugins = sample_config.get_active_plugins()
        assert isinstance(plugins, set)
        assert "PCEStdout" in plugins

    def test_get_plugin_config(self, sample_config: AppConfig) -> None:
        plugin_cfg = sample_config.get_plugin_config("PCEStdout")
        assert isinstance(plugin_cfg, dict)
        assert plugin_cfg["prepend"] == "Pretty cool events: "

    def test_get_plugin_config_unknown(self, sample_config: AppConfig) -> None:
        # Unknown plugin returns raw dict (empty)
        plugin_cfg = sample_config.get_plugin_config("UnknownPlugin")
        assert plugin_cfg == {}

    def test_save_config(self, sample_config: AppConfig, tmp_path: Path) -> None:
        save_path = tmp_path / "saved_config.yaml"
        save_config(sample_config, save_path, backup=False)
        reloaded = load_config(save_path)

        assert reloaded.pce.pce == sample_config.pce.pce
        assert reloaded.pce.pce_org == sample_config.pce.pce_org
        assert reloaded.pce.pce_poll_interval == sample_config.pce.pce_poll_interval
        assert reloaded.pce.pce_api_secret == sample_config.pce.pce_api_secret
        assert "PCEStdout" in reloaded.get_active_plugins()

    def test_load_event_types(self) -> None:
        event_types = load_event_types()
        assert isinstance(event_types, list)
        assert len(event_types) > 0
        # Check for some known types
        assert "user.login" in event_types or "agent.activate" in event_types

    def test_watcher_validation_missing_plugin(self, tmp_path: Path) -> None:
        """Watchers with missing plugin field should fail validation."""
        bad_config = {
            "config": {
                "pce": "pce.example.com",
                "pce_api_user": "api_test",
                "pce_api_secret": "secret",
                "pce_org": 1,
            },
            "watchers": {
                "user.login": [
                    {
                        "status": "success",
                        # Missing "plugin" key
                    },
                ],
            },
        }
        config_file = tmp_path / "bad_config.yaml"
        config_file.write_text(yaml.dump(bad_config, default_flow_style=False))
        with pytest.raises(Exception):
            load_config(config_file)
