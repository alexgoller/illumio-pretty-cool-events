"""Tests for the file output plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pretty_cool_events.plugins.file import FilePlugin


class TestFilePlugin:
    def test_file_output(self, sample_event: dict[str, Any], tmp_path: Path) -> None:
        logfile = tmp_path / "test_events.log"

        plugin = FilePlugin()
        plugin.configure({"logfile": str(logfile), "template": "default.html"})

        template_globals = {"pce_fqdn": "pce.example.com", "pce_org": 1}

        plugin.send(sample_event, {"template": "default.html"}, template_globals)

        assert logfile.exists()
        content = logfile.read_text()
        assert len(content) > 0
