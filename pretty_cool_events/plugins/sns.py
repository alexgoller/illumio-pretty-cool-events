"""AWS SNS output plugin."""

from __future__ import annotations

import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class SNSPlugin(OutputPlugin):
    """Send rendered events via AWS SNS (SMS)."""

    name = "PCESNS"

    def configure(self, config: dict[str, Any]) -> None:
        self.access_key = config.get("access_key", "")
        self.access_key_secret = config.get("access_key_secret", "")
        self.aws_region_name = config.get("aws_region_name", "us-east-1")
        self.template = config.get("template", "sms.tmpl")
        self._configured = True

    def send(
        self,
        event: dict[str, Any],
        extra_data: dict[str, Any],
        template_globals: dict[str, Any],
    ) -> None:
        import boto3

        template_name = extra_data.get("template", self.template)
        phone_number = extra_data.get("phone_number", "")

        if not phone_number:
            logger.warning("SNSPlugin: no phone_number provided in extra_data")
            return

        try:
            rendered = self.render_template(template_name, event, template_globals)

            client = boto3.client(
                "sns",
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.access_key_secret,
                region_name=self.aws_region_name,
            )
            response = client.publish(PhoneNumber=phone_number, Message=rendered)
            logger.info("Sent SNS message: %s", response.get("MessageId", ""))
        except Exception as e:
            logger.error("SNSPlugin failed to send: %s", e)
