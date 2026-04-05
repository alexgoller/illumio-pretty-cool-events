"""File output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class FilePlugin(OutputPlugin):
    """Append rendered events to a file."""

    name = "PCEFile"

    def configure(self, config: dict[str, Any]) -> None:
        self.logfile = config.get("logfile", "pce_events.log")
        self.template = config.get("template", "default.html")
        self._configured = True

    def send(
        self,
        event: dict[str, Any],
        extra_data: dict[str, Any],
        template_globals: dict[str, Any],
    ) -> None:
        template_name = extra_data.get("template", self.template)

        try:
            rendered = self.render_template(template_name, event, template_globals)

            with open(self.logfile, "a", encoding="utf-8") as f:
                f.write(rendered)
                f.write("\n")

            logger.info("Wrote event to file: %s", self.logfile)
        except Exception as e:
            logger.error("FilePlugin failed to write: %s", e)
