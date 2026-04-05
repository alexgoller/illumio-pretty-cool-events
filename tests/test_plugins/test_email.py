"""Tests for the email output plugin."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from pretty_cool_events.plugins.email import EmailPlugin


class TestEmailPlugin:
    def test_email_send(self, sample_event: dict[str, Any]) -> None:
        plugin = EmailPlugin()
        plugin.configure({
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_user": "user@example.com",
            "smtp_password": "password",
            "email_from": "pce@example.com",
            "email_to": "admin@example.com",
            "template": "default.html",
        })

        template_globals = {"pce_fqdn": "pce.example.com", "pce_org": 1}

        mock_server = MagicMock()

        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

            plugin.send(sample_event, {"template": "default.html"}, template_globals)

            mock_smtp_class.assert_called_once_with("smtp.example.com", 587)
            mock_server.sendmail.assert_called_once()
            call_args = mock_server.sendmail.call_args
            assert call_args[0][0] == "pce@example.com"
            assert call_args[0][1] == ["admin@example.com"]

    def test_email_port_config(self) -> None:
        """Verify smtp_port is correctly read from config (regression test)."""
        plugin = EmailPlugin()
        plugin.configure({"smtp_port": 465})
        assert plugin.smtp_port == 465

        plugin2 = EmailPlugin()
        plugin2.configure({"smtp_port": 25})
        assert plugin2.smtp_port == 25
