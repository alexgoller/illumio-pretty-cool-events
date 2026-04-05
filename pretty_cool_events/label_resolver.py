"""Resolve human-readable label expressions to PCE label hrefs.

Supports expressions like:
    "env=prod, bu=banking"              -> AND of two labels
    "env=prod AND app=payment"          -> same
    "role=web | role=processing"        -> OR (separate include groups)

Used by the traffic explorer to let users write natural queries
instead of dealing with /orgs/1/labels/17 hrefs.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class LabelResolver:
    """Caches PCE labels and resolves key=value expressions to hrefs."""

    def __init__(self) -> None:
        self._labels: list[dict[str, Any]] = []
        self._by_key_value: dict[tuple[str, str], str] = {}
        self._keys: set[str] = set()

    def load(self, labels: list[dict[str, Any]]) -> None:
        """Load labels from the PCE (call with pce_client.get_labels() result)."""
        self._labels = labels
        self._by_key_value = {}
        self._keys = set()
        for label in labels:
            key = label.get("key", "")
            value = label.get("value", "")
            href = label.get("href", "")
            if key and value and href:
                self._by_key_value[(key, value)] = href
                self._keys.add(key)

    @property
    def label_keys(self) -> list[str]:
        return sorted(self._keys)

    def values_for_key(self, key: str) -> list[str]:
        return sorted(v for (k, v) in self._by_key_value if k == key)

    def all_labels(self) -> list[dict[str, str]]:
        """Return all labels as {key, value, href} dicts."""
        return [
            {"key": k, "value": v, "href": self._by_key_value[(k, v)]}
            for (k, v) in sorted(self._by_key_value.keys())
        ]

    def resolve(self, key: str, value: str) -> str | None:
        """Resolve a single key=value to its href."""
        return self._by_key_value.get((key, value))

    def parse_expression(self, expr: str) -> list[list[dict[str, Any]]]:
        """Parse a label expression into the PCE include format.

        Format: [[{label: {href: ...}}, ...], ...]
        - Inner list = AND (all labels must match on the same workload)
        - Outer list = OR (any group can match)

        Supports:
            "env=prod, app=payment"         -> [[env_href, app_href]]
            "env=prod AND app=payment"      -> [[env_href, app_href]]
            "role=web OR role=db"           -> [[web_href], [db_href]]
            "" (empty)                      -> []
        """
        expr = expr.strip()
        if not expr:
            return []

        # Split on OR first
        or_groups = re.split(r'\s+OR\s+|\s*\|\s*', expr, flags=re.IGNORECASE)

        result: list[list[dict[str, Any]]] = []
        for group in or_groups:
            # Split on AND / comma
            parts = re.split(r'\s+AND\s+|\s*,\s*', group.strip(), flags=re.IGNORECASE)
            label_refs: list[dict[str, Any]] = []
            for part in parts:
                part = part.strip()
                if "=" not in part:
                    continue
                key, value = part.split("=", 1)
                key, value = key.strip(), value.strip()
                href = self.resolve(key, value)
                if href:
                    label_refs.append({"label": {"href": href}})
                else:
                    logger.warning("Label not found: %s=%s", key, value)
            if label_refs:
                result.append(label_refs)

        return result

    def parse_exclude(self, expr: str) -> list[dict[str, Any]]:
        """Parse an exclude expression (flat list, no OR grouping).

        "env=dev, env=staging" -> [{label: {href: ...}}, {label: {href: ...}}]
        """
        expr = expr.strip()
        if not expr:
            return []

        parts = re.split(r'\s*,\s*|\s+AND\s+', expr, flags=re.IGNORECASE)
        refs: list[dict[str, Any]] = []
        for part in parts:
            part = part.strip()
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            href = self.resolve(key.strip(), value.strip())
            if href:
                refs.append({"label": {"href": href}})
        return refs

    def parse_services(self, expr: str) -> list[dict[str, Any]]:
        """Parse a services expression into port/protocol dicts.

        "443/tcp, 80/tcp"       -> [{"port": 443, "proto": 6}, {"port": 80, "proto": 6}]
        "5432/tcp"              -> [{"port": 5432, "proto": 6}]
        "53/udp"                -> [{"port": 53, "proto": 17}]
        "3306"                  -> [{"port": 3306, "proto": 6}]  (defaults to TCP)
        ""                      -> []
        """
        proto_map = {"tcp": 6, "udp": 17, "icmp": 1}
        expr = expr.strip()
        if not expr:
            return []

        result: list[dict[str, Any]] = []
        for part in re.split(r'\s*,\s*', expr):
            part = part.strip()
            if "/" in part:
                port_str, proto_str = part.split("/", 1)
                proto = proto_map.get(proto_str.lower(), 6)
                try:
                    result.append({"port": int(port_str), "proto": proto})
                except ValueError:
                    continue
            elif part.isdigit():
                result.append({"port": int(part), "proto": 6})
        return result
