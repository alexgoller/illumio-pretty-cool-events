"""Event enrichment: workload resolution, policy diffing, runbook links."""

from __future__ import annotations

import importlib.resources
import logging
import re
import threading
import time
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Runbook lookup
# ---------------------------------------------------------------------------

_runbook_data: dict[str, Any] | None = None


def load_runbooks() -> dict[str, Any]:
    """Load runbook taxonomy from the data directory."""
    global _runbook_data
    if _runbook_data is not None:
        return _runbook_data

    data_path = importlib.resources.files("pretty_cool_events") / "data" / "runbooks.yaml"
    with importlib.resources.as_file(data_path) as p, open(p) as f:
        _runbook_data = yaml.safe_load(f)
    return _runbook_data or {}


def get_runbook(event_type: str) -> dict[str, str] | None:
    """Look up runbook info for an event type. Returns {category, url, response, severity_hint}."""
    data = load_runbooks()
    categories = data.get("categories", {})

    for cat_name, cat in categories.items():
        for pattern in cat.get("patterns", []):
            if pattern == event_type:
                return {
                    "category": cat_name,
                    "url": cat.get("runbook_url", ""),
                    "response": cat.get("response", "").strip(),
                    "severity_hint": cat.get("severity_hint", "info"),
                }
            # Regex match for wildcard patterns
            if "*" in pattern or "." in pattern:
                try:
                    if re.match(f"^{pattern}$", event_type):
                        return {
                            "category": cat_name,
                            "url": cat.get("runbook_url", ""),
                            "response": cat.get("response", "").strip(),
                            "severity_hint": cat.get("severity_hint", "info"),
                        }
                except re.error:
                    pass
    return None


def get_all_runbooks() -> dict[str, Any]:
    """Return the full runbook taxonomy for the Guide page."""
    return load_runbooks().get("categories", {})


# ---------------------------------------------------------------------------
# Resource cache (workloads, labels, policies)
# ---------------------------------------------------------------------------

class ResourceCache:
    """LRU cache for PCE resources with TTL. Thread-safe."""

    def __init__(self, max_size: int = 1000, ttl: int = 900) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, Any]] = {}
        self._max_size = max_size
        self._ttl = ttl

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, val = entry
            if time.monotonic() - ts > self._ttl:
                del self._cache[key]
                return None
            return val

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                # Evict oldest
                oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
                del self._cache[oldest_key]
            self._cache[key] = (time.monotonic(), value)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)


# ---------------------------------------------------------------------------
# Event enricher
# ---------------------------------------------------------------------------

class EventEnricher:
    """Enriches events with workload data, policy diffs, and runbook links."""

    def __init__(self, pce_client: Any | None = None) -> None:
        self._pce = pce_client
        self._workload_cache = ResourceCache(max_size=1000, ttl=900)
        self._label_cache = ResourceCache(max_size=2000, ttl=1800)
        self._resource_cache = ResourceCache(max_size=500, ttl=300)

    def enrich(self, event: dict[str, Any]) -> dict[str, Any]:
        """Enrich an event with workload data, policy diffs, and runbook."""
        event_type = event.get("event_type", "")

        # Runbook link
        runbook = get_runbook(event_type)
        if runbook:
            event["_runbook"] = runbook

        # Policy diff (works without PCE API - parses resource_changes)
        self._enrich_policy_diff(event)

        # Workload enrichment (needs PCE API for href resolution)
        if self._pce:
            self._enrich_workloads(event)

        return event

    def _enrich_workloads(self, event: dict[str, Any]) -> None:
        """Resolve workload hrefs to hostname + labels."""
        hrefs = self._extract_workload_hrefs(event)
        if not hrefs:
            return

        enriched: dict[str, dict[str, Any]] = {}
        for href in hrefs:
            wl = self._resolve_workload(href)
            if wl:
                labels = {}
                for lbl in wl.get("labels", []):
                    labels[lbl.get("key", "")] = lbl.get("value", "")
                    # Add to label cache
                    lbl_href = lbl.get("href", "")
                    if lbl_href:
                        self._label_cache.put(lbl_href, lbl)

                enriched[href] = {
                    "hostname": wl.get("hostname", ""),
                    "labels": labels,
                    "managed": wl.get("managed", False),
                    "online": wl.get("online", False),
                    "enforcement_mode": wl.get("enforcement_mode", ""),
                    "os_detail": wl.get("os_detail", ""),
                }

        if enriched:
            event["_workloads"] = enriched

    def _extract_workload_hrefs(self, event: dict[str, Any]) -> set[str]:
        """Find all workload hrefs referenced in an event."""
        hrefs: set[str] = set()
        self._scan_for_hrefs(event, hrefs, "/workloads/")
        return hrefs

    def _scan_for_hrefs(self, obj: Any, found: set[str], pattern: str) -> None:
        """Recursively scan for href strings matching a pattern."""
        if isinstance(obj, str) and pattern in obj and obj.startswith("/orgs/"):
            found.add(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                self._scan_for_hrefs(v, found, pattern)
        elif isinstance(obj, list):
            for item in obj:
                self._scan_for_hrefs(item, found, pattern)

    def _resolve_workload(self, href: str) -> dict[str, Any] | None:
        """Resolve a workload href, using cache."""
        cached = self._workload_cache.get(href)
        if cached is not None:
            return cached

        try:
            r = self._pce._request("get", f"/api/v2{href}")
            r.raise_for_status()
            wl = r.json()
            self._workload_cache.put(href, wl)
            return wl
        except Exception:
            logger.debug("Failed to resolve workload: %s", href)
            return None

    def _enrich_policy_diff(self, event: dict[str, Any]) -> None:
        """Build human-readable policy diff from resource_changes."""
        changes = event.get("resource_changes", [])
        if not changes:
            return

        diffs: list[str] = []
        for rc in changes:
            change_type = rc.get("change_type", "")
            resource = rc.get("resource", {})
            field_changes = rc.get("changes")

            # Identify resource type and name
            res_type = ""
            res_name = ""
            res_href = ""
            for rtype, rdata in resource.items():
                res_type = rtype
                if isinstance(rdata, dict):
                    res_name = rdata.get("name", "")
                    res_href = rdata.get("href", "")
                break

            if change_type == "delete":
                diffs.append(f"DELETED {res_type} '{res_name or res_href}'")
            elif change_type == "create":
                diffs.append(f"CREATED {res_type} '{res_name or res_href}'")
            elif change_type == "update" and isinstance(field_changes, dict):
                for field, diff in field_changes.items():
                    if isinstance(diff, dict):
                        before = diff.get("before")
                        after = diff.get("after")
                        before_str = str(before) if before is not None else "null"
                        after_str = str(after) if after is not None else "null"
                        diffs.append(
                            f"UPDATED {res_type} '{res_name or res_href}': "
                            f"{field} changed from {before_str} to {after_str}"
                        )

        if diffs:
            event["_policy_diff"] = "\n".join(diffs)
            event["_policy_diff_lines"] = diffs
