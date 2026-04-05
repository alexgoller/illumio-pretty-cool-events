"""ServiceNow output plugin."""

from __future__ import annotations

import json
import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class ServiceNowPlugin(OutputPlugin):
    """Create ServiceNow incidents from rendered events."""

    name = "PCEServiceNow"

    def configure(self, config: dict[str, Any]) -> None:
        self.instance = config.get("instance", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
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

            url = f"https://{self.instance}.service-now.com/api/now/table/incident"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            payload = json.dumps({
                "short_description": extra_data.get("short_description", "PCE Event"),
                "description": rendered,
                "urgency": extra_data.get("urgency", "2"),
                "impact": extra_data.get("impact", "2"),
            })

            response = httpx.post(
                url,
                content=payload,
                headers=headers,
                auth=(self.username, self.password),
            )
            response.raise_for_status()
            result = response.json()
            logger.info(
                "Created ServiceNow incident: %s",
                result.get("result", {}).get("number", "unknown"),
            )
        except Exception as e:
            logger.error("ServiceNowPlugin failed to create incident: %s", e)
