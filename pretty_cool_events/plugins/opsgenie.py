"""Opsgenie output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class OpsgeniePlugin(OutputPlugin):
    """Create Opsgenie alerts for on-call notification."""

    name = "PCEOpsgenie"

    def configure(self, config: dict[str, Any]) -> None:
        self.api_key = config.get("api_key", "")
        self.team = config.get("team", "")
        self.priority = config.get("priority", "P3")
        self.tags = config.get("tags", "illumio,pce")
        self.template = config.get("template", "default.html")
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

            alert: dict[str, Any] = {
                "message": f"PCE: {event.get('event_type', 'unknown')}",
                "description": rendered,
                "priority": extra_data.get("priority", self.priority),
                "tags": [t.strip() for t in self.tags.split(",") if t.strip()],
            }

            if self.team:
                alert["responders"] = [{"name": self.team, "type": "team"}]

            response = httpx.post(
                "https://api.opsgenie.com/v2/alerts",
                json=alert,
                headers={
                    "Authorization": f"GenieKey {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            logger.info("Created Opsgenie alert for %s", event.get("event_type"))
        except Exception as e:
            logger.error("OpsgeniePlugin failed: %s", e)
