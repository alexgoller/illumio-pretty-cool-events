"""Event watcher matching logic with flexible field-level filtering."""

from __future__ import annotations

import logging
import re
from typing import Any

from pretty_cool_events.config import WatcherAction

logger = logging.getLogger(__name__)


def _value_matches(pattern: str, value: str | None) -> bool:
    """Check if a filter pattern matches a value.

    Supports:
    - "*" or "any" matches everything (including None)
    - "!" prefix negates the match (e.g., "!success" matches anything except "success")
    - "val1|val2" matches any of the pipe-separated values
    - Regex if the pattern contains metacharacters
    - Exact match otherwise
    - None values are normalized to empty string for comparison
    """
    if pattern in ("*", "any"):
        return True

    normalized = value if value is not None else ""

    # Negation
    if pattern.startswith("!"):
        return not _value_matches(pattern[1:], value)

    # Pipe-separated alternatives
    if "|" in pattern and not any(c in pattern for c in r".*+?[](){}^$\\"):
        return normalized in pattern.split("|")

    # Regex matching (if metacharacters present beyond simple pipe)
    if any(c in pattern for c in r".*+?[](){}^$\\"):
        try:
            return bool(re.match(f"^{pattern}$", normalized))
        except re.error:
            return pattern == normalized

    # Exact match
    return pattern == normalized


def _extract_nested(event: dict[str, Any], field_path: str) -> str | None:
    """Extract a value from a nested event dict using dot notation.

    Supports dicts and lists. For a list, a numeric segment indexes into it
    (e.g. "notifications.0.info.api_endpoint"); a non-numeric segment is
    searched across every element, returning the first match (e.g.
    "notifications.info.api_endpoint" finds the field in any notification).

    Examples:
        "event_type" -> event["event_type"]
        "created_by.user.username" -> event["created_by"]["user"]["username"]
        "action.src_ip" -> event["action"]["src_ip"]
        "notifications.info.api_endpoint" -> first notification's api_endpoint
    """
    def walk(current: Any, parts: list[str]) -> Any:
        if not parts:
            return current
        part, rest = parts[0], parts[1:]
        if isinstance(current, dict):
            if part in current:
                return walk(current[part], rest)
            return None
        if isinstance(current, list):
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(current):
                    return walk(current[idx], rest)
                return None
            # Non-numeric segment: search every element for the remaining path.
            for el in current:
                found = walk(el, [part] + rest)
                if found is not None:
                    return found
            return None
        return None

    result = walk(event, field_path.split("."))
    if result is None or isinstance(result, str):
        return result
    return str(result)


class WatcherRegistry:
    """Compiles watcher patterns and matches incoming events.

    Supports flexible matching on any event field via the `match_fields` dict
    in extra_data. If no match_fields are present, falls back to matching on
    event_type (pattern key) + status (action.status).
    """

    def __init__(self, watchers: dict[str, list[WatcherAction]]) -> None:
        self._exact: dict[str, list[WatcherAction]] = {}
        self._regex: list[tuple[re.Pattern[str], list[WatcherAction]]] = []

        for pattern, actions in watchers.items():
            if any(c in pattern for c in r".*+?[](){}^$|\\"):
                try:
                    compiled = re.compile(
                        f"^{pattern}$" if not pattern.startswith("^") else pattern
                    )
                    self._regex.append((compiled, actions))
                    logger.info("Compiled regex watcher: %s", pattern)
                except re.error as e:
                    logger.error("Invalid regex pattern '%s': %s", pattern, e)
            else:
                self._exact[pattern] = actions
                logger.info("Registered exact watcher: %s", pattern)

    def match(self, event: dict[str, Any]) -> list[tuple[WatcherAction, dict[str, Any]]]:
        """Match an event against all watchers.

        Returns list of (action, extra_data) tuples for all matching watchers.
        """
        event_type = event.get("event_type", "")
        results: list[tuple[WatcherAction, dict[str, Any]]] = []

        # Try exact match first (O(1))
        if event_type in self._exact:
            for action in self._exact[event_type]:
                if self._action_matches(action, event):
                    results.append((action, action.extra_data))

        # Then try regex patterns on event_type
        for pattern, actions in self._regex:
            if pattern.match(event_type):
                for action in actions:
                    if self._action_matches(action, event):
                        results.append((action, action.extra_data))

        return results

    def _action_matches(self, action: WatcherAction, event: dict[str, Any]) -> bool:
        """Check if an action's filters match the event.

        Checks action.status against event status, then checks any additional
        match_fields in extra_data against the corresponding event fields.
        """
        # Status check (always applies)
        if not _value_matches(action.status, event.get("status")):
            return False

        # Additional field matchers from extra_data.match_fields
        match_fields = action.extra_data.get("match_fields", {})
        for field_path, pattern in match_fields.items():
            actual_value = _extract_nested(event, field_path)
            if not _value_matches(str(pattern), actual_value):
                return False

        return True
