"""Tests for the CLI interface."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from pretty_cool_events.cli import cli
from tests.conftest import MINIMAL_CONFIG_YAML


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def valid_config_file(tmp_path: Path) -> Path:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(MINIMAL_CONFIG_YAML, default_flow_style=False))
    return config_file


class TestCLI:
    def test_config_validate_valid(self, runner: CliRunner, valid_config_file: Path) -> None:
        result = runner.invoke(cli, ["config", "validate", "--config", str(valid_config_file)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "Valid" in result.output

    def test_config_validate_invalid(self, runner: CliRunner, tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("not: valid: yaml: [")
        result = runner.invoke(cli, ["config", "validate", "--config", str(bad_file)])
        assert result.exit_code != 0

    def test_watcher_list(self, runner: CliRunner, valid_config_file: Path) -> None:
        result = runner.invoke(cli, ["watcher", "list", "--config", str(valid_config_file)])
        assert result.exit_code == 0
        assert "user.login" in result.output

    def test_config_show(self, runner: CliRunner, valid_config_file: Path) -> None:
        result = runner.invoke(cli, ["config", "show", "--config", str(valid_config_file)])
        assert result.exit_code == 0
        # Secrets should be masked
        assert "****" in result.output
