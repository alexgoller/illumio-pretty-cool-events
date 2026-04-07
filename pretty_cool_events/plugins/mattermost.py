"""Mattermost output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class MattermostPlugin(OutputPlugin):
    """Send notifications to Mattermost channels via incoming webhook."""

    name = "PCEMattermost"

    def configure(self, config: dict[str, Any]) -> None:
        self.webhook_url = config.get("webhook_url", "")
        self.channel = config.get("channel", "")
        self.username = config.get("username", "Pretty Cool Events")
        self.icon_url = config.get("icon_url", "")
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
        channel = extra_data.get("channel", self.channel)

        if not self.webhook_url:
            logger.error("MattermostPlugin: no webhook_url configured")
            return

        try:
            rendered = self.render_template(template_name, event, template_globals)

            payload: dict[str, Any] = {"text": rendered}
            if channel:
                payload["channel"] = channel
            if self.username:
                payload["username"] = self.username
            if self.icon_url:
                payload["icon_url"] = self.icon_url

            response = httpx.post(self.webhook_url, json=payload)
            response.raise_for_status()
            logger.info("Posted Mattermost message to %s", channel or "default")
        except Exception as e:
            logger.error("MattermostPlugin failed: %s", e)
