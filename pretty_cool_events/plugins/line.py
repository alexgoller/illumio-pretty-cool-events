"""LINE Messaging API output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class LinePlugin(OutputPlugin):
    """Send notifications via LINE Messaging API (push message)."""

    name = "PCELine"

    def configure(self, config: dict[str, Any]) -> None:
        self.channel_access_token = config.get("channel_access_token", "")
        self.to = config.get("to", "")  # user ID, group ID, or room ID
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
        to = extra_data.get("to", self.to)

        if not self.channel_access_token or not to:
            logger.error("LinePlugin: channel_access_token and to (user/group ID) required")
            return

        try:
            rendered = self.render_template(template_name, event, template_globals)

            response = httpx.post(
                "https://api.line.me/v2/bot/message/push",
                json={
                    "to": to,
                    "messages": [
                        {"type": "text", "text": rendered},
                    ],
                },
                headers={
                    "Authorization": f"Bearer {self.channel_access_token}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            logger.info("Sent LINE message to %s", to)
        except Exception as e:
            logger.error("LinePlugin failed: %s", e)
