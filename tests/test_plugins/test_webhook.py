"""Tests for the webhook output plugin."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from pretty_cool_events.plugins.webhook import WebhookPlugin


class TestWebhookPlugin:
    def test_webhook_send(self, sample_event: dict[str, Any]) -> None:
        plugin = WebhookPlugin()
        plugin.configure({
            "url": "https://hooks.example.com/notify",
            "bearer_token": "my-secret-token",
        })

        template_globals = {"pce_fqdn": "pce.example.com", "pce_org": 1}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        # httpx is imported inside send(), so patch it at the module level
        with patch("httpx.post", return_value=mock_response) as mock_post:
            plugin.send(sample_event, {}, template_globals)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer my-secret-token"
        assert call_kwargs.args[0] == "https://hooks.example.com/notify"
