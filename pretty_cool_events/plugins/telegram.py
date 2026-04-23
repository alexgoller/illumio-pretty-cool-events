"""Telegram output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class TelegramPlugin(OutputPlugin):
    """Send notifications via Telegram Bot API."""

    name = "PCETelegram"

    def configure(self, config: dict[str, Any]) -> None:
        self.bot_token = config.get("bot_token", "")
        self.chat_id = config.get("chat_id", "")
        self.parse_mode = config.get("parse_mode", "HTML")
        self.disable_preview = config.get("disable_web_page_preview", True)
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
        chat_id = extra_data.get("chat_id", self.chat_id)

        if not self.bot_token or not chat_id:
            logger.error("TelegramPlugin: bot_token and chat_id required")
            return

        try:
            rendered = self.render_template(template_name, event, template_globals)

            response = httpx.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": rendered,
                    "parse_mode": self.parse_mode,
                    "disable_web_page_preview": self.disable_preview,
                },
            )
            response.raise_for_status()
            logger.info("Sent Telegram message to chat %s", chat_id)
        except Exception as e:
            logger.error("TelegramPlugin failed: %s", e)
