"""Email output plugin."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from pretty_cool_events.plugins.base import OutputPlugin

logger = logging.getLogger(__name__)


class EmailPlugin(OutputPlugin):
    """Send rendered events via email."""

    name = "PCEMail"

    def configure(self, config: dict[str, Any]) -> None:
        self.smtp_host = config.get("smtp_host", "localhost")
        self.smtp_port = config.get("smtp_port", 587)
        self.smtp_user = config.get("smtp_user", "")
        self.smtp_password = config.get("smtp_password", "")
        self.email_from = config.get("email_from", "")
        self.email_to = config.get("email_to", "")
        self.template = config.get("template", "email.tmpl")
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

            msg = MIMEMultipart("alternative")
            msg["Subject"] = extra_data.get("subject", "PCE Event Notification")
            msg["From"] = self.email_from
            msg["To"] = self.email_to

            msg.attach(MIMEText(rendered, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.email_from, self.email_to.split(","), msg.as_string())

            logger.info("Sent email to %s", self.email_to)
        except Exception as e:
            logger.error("EmailPlugin failed to send: %s", e)
