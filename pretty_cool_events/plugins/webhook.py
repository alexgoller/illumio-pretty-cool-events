"""Webhook output plugin."""

from __future__ import annotations

import json
import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class WebhookPlugin(OutputPlugin):
    """Send rendered events to a webhook endpoint."""

    name = "PCEWebhook"

    def configure(self, config: dict[str, Any]) -> None:
        self.url = config.get("url", "")
        self.bearer_token = config.get("bearer_token", "")
        self.data = config.get("data", "")
        self.template = config.get("template", "")
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
            if template_name:
                payload = self.render_template(template_name, event, template_globals)
            else:
                payload = json.dumps(event)

            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self.bearer_token:
                headers["Authorization"] = f"Bearer {self.bearer_token}"

            response = httpx.post(self.url, content=payload, headers=headers)
            response.raise_for_status()
            logger.info("Webhook POST to %s returned %s", self.url, response.status_code)
        except Exception as e:
            logger.error("WebhookPlugin failed to send: %s", e)
