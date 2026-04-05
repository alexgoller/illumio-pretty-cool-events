"""Tests for the stdout output plugin."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from pretty_cool_events.plugins.stdout import StdoutPlugin


class TestStdoutPlugin:
    def test_stdout_output(
        self, sample_event: dict[str, Any], caplog: pytest.LogCaptureFixture
    ) -> None:
        plugin = StdoutPlugin()
        plugin.configure({"prepend": "TEST: ", "append": ""})

        template_globals = {"pce_fqdn": "pce.example.com", "pce_org": 1}

        with caplog.at_level(logging.INFO):
            plugin.send(sample_event, {"template": "default.html"}, template_globals)

        assert any("TEST: " in record.message for record in caplog.records)
