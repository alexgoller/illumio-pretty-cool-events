"""PCE API client using httpx."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3


class PCEClient:
    """Communicates with the Illumio PCE REST API."""

    def __init__(
        self,
        base_url: str,
        api_user: str,
        api_secret: str,
        org_id: int = 1,
        verify_tls: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._org_id = org_id
        self._timeout = timeout

        if not self._base_url.startswith("http"):
            self._base_url = f"https://{self._base_url}"

        transport = httpx.HTTPTransport(retries=MAX_RETRIES)
        self._client = httpx.Client(
            base_url=self._base_url,
            auth=(api_user, api_secret),
            verify=verify_tls,
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": "pretty-cool-events/1.0"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PCEClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def health_check(self) -> bool:
        """Check PCE connectivity."""
        try:
            r = self._client.get("/api/v2/health")
            return r.status_code == 200
        except httpx.HTTPError as e:
            logger.error("PCE health check failed: %s", e)
            return False

    def get_events(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch events from the PCE within a time window.

        Args:
            since: Only return events at or after this time.
            until: Only return events at or before this time.
            max_results: Limit the number of results returned.
        """
        params: dict[str, Any] = {}
        if since:
            params["timestamp[gte]"] = since.astimezone(timezone.utc).isoformat()
        if until:
            params["timestamp[lte]"] = until.astimezone(timezone.utc).isoformat()
        if max_results:
            params["max_results"] = max_results

        try:
            r = self._client.get(
                f"/api/v2/orgs/{self._org_id}/events",
                params=params,
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            logger.error("Failed to fetch events (HTTP %d): %s", e.response.status_code, e)
            return []
        except httpx.HTTPError as e:
            logger.error("Failed to fetch events: %s", e)
            return []

    def get_traffic(self, query: dict[str, Any]) -> dict[str, Any] | None:
        """Submit a traffic analysis query."""
        try:
            r = self._client.post(
                f"/api/v2/orgs/{self._org_id}/traffic_flows/traffic_analysis_queries",
                json=query,
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error("Traffic query failed: %s", e)
            return None
