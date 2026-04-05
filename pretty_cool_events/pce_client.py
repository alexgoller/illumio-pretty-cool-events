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

    def health_check(self, timeout: float = 10.0) -> bool:
        """Check PCE connectivity with a short timeout."""
        try:
            r = self._client.get("/api/v2/health", timeout=timeout)
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
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            # Connection-level failures bubble up so the event loop can track them
            logger.error("PCE connection failed: %s", e)
            raise
        except httpx.HTTPError as e:
            logger.error("Failed to fetch events: %s", e)
            raise

    # ------------------------------------------------------------------
    # Traffic flow async queries
    # ------------------------------------------------------------------

    def get_labels(self) -> list[dict[str, Any]]:
        """Fetch all labels from the PCE."""
        try:
            r = self._client.get(f"/api/v2/orgs/{self._org_id}/labels")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch labels: %s", e)
            return []

    def create_traffic_query(self, query: dict[str, Any]) -> dict[str, Any] | None:
        """Submit an async traffic flow query. Returns the query object with href."""
        try:
            r = self._client.post(
                f"/api/v2/orgs/{self._org_id}/traffic_flows/async_queries",
                json=query,
            )
            if r.status_code == 202:
                # 202 Accepted - get query href from listing
                return {"status": "queued", "accepted": True}
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error("Traffic query creation failed: %s", e)
            return None

    def list_traffic_queries(self) -> list[dict[str, Any]]:
        """List all async traffic queries."""
        try:
            r = self._client.get(
                f"/api/v2/orgs/{self._org_id}/traffic_flows/async_queries"
            )
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error("Failed to list traffic queries: %s", e)
            return []

    def get_traffic_query(self, href: str) -> dict[str, Any] | None:
        """Get the status of an async traffic query by href."""
        try:
            path = href if href.startswith("/api/") else f"/api/v2{href}"
            r = self._client.get(path)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error("Failed to get traffic query: %s", e)
            return None

    def download_traffic_results(self, href: str) -> str | None:
        """Download traffic query results as CSV."""
        try:
            path = href if href.startswith("/api/") else f"/api/v2{href}"
            r = self._client.get(path)
            r.raise_for_status()
            return r.text
        except httpx.HTTPError as e:
            logger.error("Failed to download traffic results: %s", e)
            return None
