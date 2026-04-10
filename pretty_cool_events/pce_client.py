"""PCE API client using httpx."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


class PCEClient:
    """Communicates with the Illumio PCE REST API.

    Uses a fresh httpx.Client for every request to avoid stale connection
    pool issues in Docker/containerized environments. Each request creates
    a new TCP+TLS connection (~0.6s overhead), which is acceptable for a
    polling-based system making requests every 10-60 seconds.
    """

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

        if not self._base_url.startswith("http"):
            self._base_url = f"https://{self._base_url}"

        self._client_args = {
            "base_url": self._base_url,
            "auth": (api_user, api_secret),
            "timeout": httpx.Timeout(timeout, connect=timeout),
            "verify": verify_tls,
            "headers": {"User-Agent": "pretty-cool-events/1.0"},
        }
        # Serialize requests to prevent overloading the PCE
        self._lock = threading.Lock()
        self._web_lock = threading.Lock()

    def close(self) -> None:
        pass

    def __enter__(self) -> PCEClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _request(self, method: str, path: str, web: bool = False,
                 **kwargs: Any) -> httpx.Response:
        """Make an HTTP request with a fresh client."""
        lock = self._web_lock if web else self._lock
        with lock, httpx.Client(**self._client_args) as client:
            return getattr(client, method)(path, **kwargs)

    def health_check(self) -> bool:
        """Check PCE connectivity."""
        try:
            r = self._request("get", "/api/v2/health")
            return r.status_code == 200
        except httpx.HTTPError as e:
            logger.error("PCE health check failed: %s", e)
            return False

    def get_events(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        max_results: int | None = None,
        web: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch events from the PCE within a time window."""
        params: dict[str, Any] = {}
        if since:
            params["timestamp[gte]"] = since.astimezone(timezone.utc).isoformat()
        if until:
            params["timestamp[lte]"] = until.astimezone(timezone.utc).isoformat()
        if max_results:
            params["max_results"] = max_results

        try:
            r = self._request("get", f"/api/v2/orgs/{self._org_id}/events",
                              web=web, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            logger.error("Failed to fetch events (HTTP %d): %s", e.response.status_code, e)
            return []
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            logger.error("PCE connection failed: %s", e)
            raise
        except httpx.HTTPError as e:
            logger.error("Failed to fetch events: %s", e)
            raise

    # ------------------------------------------------------------------
    # Traffic flow async queries
    # ------------------------------------------------------------------

    def get_labels(self, web: bool = False) -> list[dict[str, Any]]:
        """Fetch all labels from the PCE."""
        try:
            r = self._request("get", f"/api/v2/orgs/{self._org_id}/labels", web=web)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error("Failed to fetch labels: %s", e)
            return []

    def create_traffic_query(self, query: dict[str, Any], web: bool = False) -> dict[str, Any] | None:
        """Submit an async traffic flow query."""
        try:
            r = self._request("post",
                              f"/api/v2/orgs/{self._org_id}/traffic_flows/async_queries",
                              web=web, json=query)
            if r.status_code == 202:
                return {"status": "queued", "accepted": True}
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error("Traffic query creation failed: %s", e)
            return None

    def list_traffic_queries(self, web: bool = False) -> list[dict[str, Any]]:
        """List all async traffic queries."""
        try:
            r = self._request("get",
                              f"/api/v2/orgs/{self._org_id}/traffic_flows/async_queries",
                              web=web)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error("Failed to list traffic queries: %s", e)
            return []

    def get_traffic_query(self, href: str, web: bool = False) -> dict[str, Any] | None:
        """Get the status of an async traffic query by href."""
        try:
            path = href if href.startswith("/api/") else f"/api/v2{href}"
            r = self._request("get", path, web=web)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            logger.error("Failed to get traffic query: %s", e)
            return None

    def download_traffic_results(self, href: str, web: bool = False) -> str | None:
        """Download traffic query results as CSV."""
        try:
            path = href if href.startswith("/api/") else f"/api/v2{href}"
            r = self._request("get", path, web=web)
            r.raise_for_status()
            return r.text
        except httpx.HTTPError as e:
            logger.error("Failed to download traffic results: %s", e)
            return None
