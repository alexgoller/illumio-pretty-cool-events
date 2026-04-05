"""Tests for the Slack output plugin."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from pretty_cool_events.plugins.slack import SlackPlugin


class TestSlackPlugin:
    def test_slack_send(self, sample_event: dict[str, Any]) -> None:
        plugin = SlackPlugin()
        plugin.configure({
            "slack_bot_token": "xoxb-test-token",
            "template": "default-slack.html",
        })

        template_globals = {"pce_fqdn": "pce.example.com", "pce_org": 1}
        extra_data = {"template": "default-slack.html", "channel": "#alerts"}

        mock_client_instance = MagicMock()
        mock_client_instance.chat_postMessage.return_value = {"ts": "1234567890.123456"}

        # WebClient is imported inside send(), so patch it in slack_sdk
        with patch("slack_sdk.WebClient", return_value=mock_client_instance):
            plugin.send(sample_event, extra_data, template_globals)

        mock_client_instance.chat_postMessage.assert_called_once()
        call_kwargs = mock_client_instance.chat_postMessage.call_args
        assert call_kwargs.kwargs["channel"] == "#alerts"
        assert "blocks" in call_kwargs.kwargs
