"""Tests for the PCE API client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from pretty_cool_events.pce_client import PCEClient


@pytest.fixture()
def pce_client() -> PCEClient:
    """Create a PCEClient with TLS verification disabled for testing."""
    return PCEClient(
        base_url="https://pce.example.com",
        api_user="api_test",
        api_secret="secret",
        org_id=1,
        verify_tls=False,
    )


class TestPCEClient:
    def test_health_check_success(self, pce_client: PCEClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch.object(pce_client._client, "get", return_value=mock_response):
            assert pce_client.health_check() is True

    def test_health_check_failure(self, pce_client: PCEClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 500
        with patch.object(pce_client._client, "get", return_value=mock_response):
            assert pce_client.health_check() is False

    def test_get_events(self, pce_client: PCEClient) -> None:
        mock_events = [
            {"event_type": "user.login", "status": "success"},
            {"event_type": "agent.activate", "status": "success"},
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = mock_events
        mock_response.raise_for_status = MagicMock()
        with patch.object(pce_client._client, "get", return_value=mock_response):
            events = pce_client.get_events()
            assert len(events) == 2
            assert events[0]["event_type"] == "user.login"

    def test_get_events_connection_error(self, pce_client: PCEClient) -> None:
        """Connection errors are re-raised so the event loop can track them."""
        with patch.object(
            pce_client._client, "get", side_effect=httpx.ConnectError("Connection refused")
        ):
            with pytest.raises(httpx.ConnectError):
                pce_client.get_events()

    def test_auto_prefix_https(self) -> None:
        client = PCEClient(
            base_url="pce.example.com",
            api_user="api_test",
            api_secret="secret",
        )
        assert client._base_url.startswith("https://")
        client.close()
