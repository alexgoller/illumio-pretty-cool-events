"""Slack output plugin."""

from __future__ import annotations

import json
import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class SlackPlugin(OutputPlugin):
    """Send rendered events to a Slack channel."""

    name = "PCESlack"

    def configure(self, config: dict[str, Any]) -> None:
        self.slack_bot_token = config.get("slack_bot_token", "")
        self.template = config.get("template", "default-slack.html")
        self._configured = True

    def send(
        self,
        event: dict[str, Any],
        extra_data: dict[str, Any],
        template_globals: dict[str, Any],
    ) -> None:
        from slack_sdk import WebClient
        from slack_sdk.errors import SlackApiError

        template_name = extra_data.get("template", self.template)
        channel = extra_data.get("channel", "")

        if not channel:
            logger.warning("SlackPlugin: no channel provided in extra_data")
            return

        try:
            rendered = self.render_template(template_name, event, template_globals)
            blocks = json.loads(rendered)
            client = WebClient(token=self.slack_bot_token)
            response = client.chat_postMessage(channel=channel, blocks=blocks)
            logger.info("Posted Slack message to %s: %s", channel, response["ts"])
        except SlackApiError as e:
            logger.error("Slack API error: %s", e.response["error"])
        except Exception as e:
            logger.error("SlackPlugin failed to send: %s", e)
