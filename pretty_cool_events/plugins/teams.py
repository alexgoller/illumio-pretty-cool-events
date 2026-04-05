"""Microsoft Teams output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class TeamsPlugin(OutputPlugin):
    """Send rendered events to a Microsoft Teams webhook."""

    name = "PCETeams"

    def configure(self, config: dict[str, Any]) -> None:
        self.webhook = config.get("webhook", "")
        self.template = config.get("template", "default-teams.tmpl")
        self._configured = True

    def send(
        self,
        event: dict[str, Any],
        extra_data: dict[str, Any],
        template_globals: dict[str, Any],
    ) -> None:
        import httpx

        template_name = extra_data.get("template", self.template)

        try:
            rendered = self.render_template(template_name, event, template_globals)

            headers = {"Content-Type": "application/json"}
            response = httpx.post(self.webhook, content=rendered, headers=headers)
            response.raise_for_status()
            logger.info("Posted Teams message: %s", response.status_code)
        except Exception as e:
            logger.error("TeamsPlugin failed to send: %s", e)
