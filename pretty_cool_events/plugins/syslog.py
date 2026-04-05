"""Syslog output plugin."""

from __future__ import annotations

import logging
import logging.handlers
import ssl
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class SyslogPlugin(OutputPlugin):
    """Send rendered events to a remote syslog server."""

    name = "PCESyslog"

    def configure(self, config: dict[str, Any]) -> None:
        self.syslog_host = config.get("syslog_host", "localhost")
        self.syslog_port = config.get("syslog_port", 514)
        self.syslog_cert_file = config.get("syslog_cert_file", "")
        self.template = config.get("template", "default.html")
        self._configured = True

    def send(
        self,
        event: dict[str, Any],
        extra_data: dict[str, Any],
        template_globals: dict[str, Any],
    ) -> None:
        template_name = extra_data.get("template", self.template)

        try:
            rendered = self.render_template(template_name, event, template_globals)

            syslog_logger = logging.getLogger(f"PCESyslog.{self.syslog_host}")
            syslog_logger.setLevel(logging.INFO)

            # Remove existing handlers to avoid duplicates
            syslog_logger.handlers.clear()

            if self.syslog_cert_file:
                ssl_context = ssl.create_default_context(cafile=self.syslog_cert_file)
                handler = logging.handlers.SysLogHandler(
                    address=(self.syslog_host, self.syslog_port),
                    socktype=__import__("socket").SOCK_STREAM,
                )
                handler.socket = ssl_context.wrap_socket(
                    handler.socket, server_hostname=self.syslog_host
                )
            else:
                handler = logging.handlers.SysLogHandler(
                    address=(self.syslog_host, self.syslog_port),
                )

            syslog_logger.addHandler(handler)
            syslog_logger.info(rendered)
            syslog_logger.removeHandler(handler)
            handler.close()

            logger.info("Sent syslog message to %s:%s", self.syslog_host, self.syslog_port)
        except Exception as e:
            logger.error("SyslogPlugin failed to send: %s", e)
