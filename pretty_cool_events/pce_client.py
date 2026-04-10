"""PCE API client using httpx."""

from __future__ import annotations

import logging
import threading
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

        # Explicit timeout for all phases (connect, read, write, pool)
        # to handle slow environments like Docker emulation
        self._httpx_timeout = httpx.Timeout(timeout, connect=timeout)

        # Disable keep-alive connection pooling. Stale pooled connections
        # cause ConnectTimeout in Docker/emulated environments. Fresh
        # connections work reliably (0.6s per request, proven via testing).
        no_keepalive = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=0,
            keepalive_expiry=0,
        )
        transport = httpx.HTTPTransport(verify=verify_tls, limits=no_keepalive)
        transport_web = httpx.HTTPTransport(verify=verify_tls, limits=no_keepalive)

        self._client_args = {
            "base_url": self._base_url,
            "auth": (api_user, api_secret),
            "timeout": self._httpx_timeout,
            "headers": {"User-Agent": "pretty-cool-events/1.0"},
        }
        self._client = httpx.Client(transport=transport, **self._client_args)
        self._web_client = httpx.Client(transport=transport_web, **self._client_args)
        # Serialize requests per client to prevent overloading the PCE
        self._lock = threading.Lock()
        self._web_lock = threading.Lock()

    def close(self) -> None:
        self._client.close()
        self._web_client.close()

    def __enter__(self) -> PCEClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _pick(self, web: bool = False) -> tuple[httpx.Client, threading.Lock]:
        """Return the appropriate client and lock (main or web)."""
        if web:
            return self._web_client, self._web_lock
        return self._client, self._lock

    def health_check(self) -> bool:
        """Check PCE connectivity using the configured timeout."""
        with self._lock:
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
        web: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch events from the PCE within a time window.

        Args:
            since: Only return events at or after this time.
            until: Only return events at or before this time.
            max_results: Limit the number of results returned.
            web: Use the web client (non-blocking with event loop).
        """
        params: dict[str, Any] = {}
        if since:
            params["timestamp[gte]"] = since.astimezone(timezone.utc).isoformat()
        if until:
            params["timestamp[lte]"] = until.astimezone(timezone.utc).isoformat()
        if max_results:
            params["max_results"] = max_results

        client, lock = self._pick(web)
        with lock:
            try:
                r = client.get(
                    f"/api/v2/orgs/{self._org_id}/events",
                    params=params,
                )
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
        client, lock = self._pick(web)
        with lock:
            try:
                r = client.get(f"/api/v2/orgs/{self._org_id}/labels")
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as e:
                logger.error("Failed to fetch labels: %s", e)
                return []

    def create_traffic_query(self, query: dict[str, Any], web: bool = False) -> dict[str, Any] | None:
        """Submit an async traffic flow query."""
        client, lock = self._pick(web)
        with lock:
            try:
                r = client.post(
                    f"/api/v2/orgs/{self._org_id}/traffic_flows/async_queries",
                    json=query,
                )
                if r.status_code == 202:
                    return {"status": "queued", "accepted": True}
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as e:
                logger.error("Traffic query creation failed: %s", e)
                return None

    def list_traffic_queries(self, web: bool = False) -> list[dict[str, Any]]:
        """List all async traffic queries."""
        client, lock = self._pick(web)
        with lock:
            try:
                r = client.get(
                    f"/api/v2/orgs/{self._org_id}/traffic_flows/async_queries"
                )
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as e:
                logger.error("Failed to list traffic queries: %s", e)
                return []

    def get_traffic_query(self, href: str, web: bool = False) -> dict[str, Any] | None:
        """Get the status of an async traffic query by href."""
        client, lock = self._pick(web)
        with lock:
            try:
                path = href if href.startswith("/api/") else f"/api/v2{href}"
                r = client.get(path)
                r.raise_for_status()
                return r.json()
            except httpx.HTTPError as e:
                logger.error("Failed to get traffic query: %s", e)
                return None

    def download_traffic_results(self, href: str, web: bool = False) -> str | None:
        """Download traffic query results as CSV."""
        client, lock = self._pick(web)
        with lock:
            try:
                path = href if href.startswith("/api/") else f"/api/v2{href}"
                r = client.get(path)
                r.raise_for_status()
                return r.text
            except httpx.HTTPError as e:
                logger.error("Failed to download traffic results: %s", e)
                return None
