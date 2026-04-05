"""Stdout output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class StdoutPlugin(OutputPlugin):
    """Print rendered events to stdout."""

    name = "PCEStdout"

    def configure(self, config: dict[str, Any]) -> None:
        self.prepend = config.get("prepend", "")
        self.append = config.get("append", "")
        self._configured = True

    def send(
        self,
        event: dict[str, Any],
        extra_data: dict[str, Any],
        template_globals: dict[str, Any],
    ) -> None:
        template_name = extra_data.get("template", "default.html")
        try:
            rendered = self.render_template(template_name, event, template_globals)
            output = f"{self.prepend}{rendered}{self.append}"
            logger.info(output)
        except Exception as e:
            logger.error("StdoutPlugin failed to render/send: %s", e)
