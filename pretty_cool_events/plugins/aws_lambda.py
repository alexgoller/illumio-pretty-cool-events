"""AWS Lambda output plugin."""

from __future__ import annotations

import json
import logging
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class LambdaPlugin(OutputPlugin):
    """Invoke AWS Lambda functions with PCE event data."""

    name = "PCELambda"

    def configure(self, config: dict[str, Any]) -> None:
        self.function_name = config.get("function_name", "")
        self.aws_region = config.get("aws_region", "us-east-1")
        self.access_key = config.get("access_key", "")
        self.access_key_secret = config.get("access_key_secret", "")
        self.invocation_type = config.get("invocation_type", "Event")  # Event=async, RequestResponse=sync
        self._configured = True

    def send(
        self,
        event: dict[str, Any],
        extra_data: dict[str, Any],
        template_globals: dict[str, Any],
    ) -> None:
        import boto3

        function_name = extra_data.get("function_name", self.function_name)
        if not function_name:
            logger.error("LambdaPlugin: no function_name configured")
            return

        try:
            payload = {
                "source": "pretty-cool-events",
                "event_type": event.get("event_type", ""),
                "pce_fqdn": template_globals.get("pce_fqdn", ""),
                "event": event,
            }

            client = boto3.client(
                "lambda",
                region_name=self.aws_region,
                aws_access_key_id=self.access_key or None,
                aws_secret_access_key=self.access_key_secret or None,
            )

            response = client.invoke(
                FunctionName=function_name,
                InvocationType=self.invocation_type,
                Payload=json.dumps(payload, default=str),
            )

            status = response.get("StatusCode", 0)
            logger.info("Invoked Lambda %s: status=%d", function_name, status)
        except Exception as e:
            logger.error("LambdaPlugin failed: %s", e)
