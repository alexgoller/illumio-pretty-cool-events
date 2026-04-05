"""Tests for the WatcherRegistry event matching logic."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from pretty_cool_events.config import WatcherAction
from pretty_cool_events.watcher import WatcherRegistry


def _make_watchers(patterns: dict[str, list[dict[str, Any]]]) -> dict[str, list[WatcherAction]]:
    """Helper to build typed watcher dicts from raw dicts."""
    result: dict[str, list[WatcherAction]] = {}
    for pattern, actions in patterns.items():
        result[pattern] = [WatcherAction(**a) for a in actions]
    return result


class TestWatcherRegistry:
    def test_exact_match(self) -> None:
        watchers = _make_watchers({
            "user.login": [{"plugin": "PCEStdout", "status": "success"}],
        })
        registry = WatcherRegistry(watchers)
        event = {"event_type": "user.login", "status": "success"}
        matches = registry.match(event)
        assert len(matches) == 1
        assert matches[0][0].plugin == "PCEStdout"

    def test_regex_match(self) -> None:
        watchers = _make_watchers({
            "user.*": [{"plugin": "PCEStdout", "status": "success"}],
        })
        registry = WatcherRegistry(watchers)
        event = {"event_type": "user.login", "status": "success"}
        matches = registry.match(event)
        assert len(matches) == 1
        assert matches[0][0].plugin == "PCEStdout"

    def test_no_match(self) -> None:
        watchers = _make_watchers({
            "user.login": [{"plugin": "PCEStdout", "status": "success"}],
        })
        registry = WatcherRegistry(watchers)
        event = {"event_type": "agent.activate", "status": "success"}
        matches = registry.match(event)
        assert len(matches) == 0

    def test_status_filter(self) -> None:
        watchers = _make_watchers({
            "user.login": [{"plugin": "PCEStdout", "status": "success"}],
        })
        registry = WatcherRegistry(watchers)
        event = {"event_type": "user.login", "status": "failure"}
        matches = registry.match(event)
        assert len(matches) == 0

    def test_multiple_matches(self) -> None:
        watchers = _make_watchers({
            "user.login": [{"plugin": "PCEStdout", "status": "success"}],
            "user.*": [{"plugin": "PCEFile", "status": "success"}],
        })
        registry = WatcherRegistry(watchers)
        event = {"event_type": "user.login", "status": "success"}
        matches = registry.match(event)
        assert len(matches) == 2
        plugin_names = {m[0].plugin for m in matches}
        assert plugin_names == {"PCEStdout", "PCEFile"}

    def test_invalid_regex(self, caplog: pytest.LogCaptureFixture) -> None:
        """Invalid regex patterns should be logged but not crash."""
        watchers = _make_watchers({
            "[invalid": [{"plugin": "PCEStdout", "status": "success"}],
        })
        with caplog.at_level(logging.ERROR):
            registry = WatcherRegistry(watchers)
        # The invalid pattern should have been logged as error
        assert any("Invalid regex" in record.message for record in caplog.records)
        # Should still work with no crash
        event = {"event_type": "anything", "status": "success"}
        matches = registry.match(event)
        assert len(matches) == 0

    def test_empty_watchers(self) -> None:
        registry = WatcherRegistry({})
        event = {"event_type": "user.login", "status": "success"}
        matches = registry.match(event)
        assert len(matches) == 0

    def test_null_status_no_match(self) -> None:
        """Events with null status should not match 'success' watchers."""
        watchers = _make_watchers({
            "user.pce_session_terminated": [{"plugin": "PCEStdout", "status": "success"}],
        })
        registry = WatcherRegistry(watchers)
        event = {"event_type": "user.pce_session_terminated", "status": None}
        matches = registry.match(event)
        assert len(matches) == 0

    def test_wildcard_status(self) -> None:
        """Watchers with status '*' should match all events including null status."""
        watchers = _make_watchers({
            "user.*": [{"plugin": "PCEStdout", "status": "*"}],
        })
        registry = WatcherRegistry(watchers)
        # Matches null status
        assert len(registry.match({"event_type": "user.login", "status": None})) == 1
        # Matches success
        assert len(registry.match({"event_type": "user.login", "status": "success"})) == 1
        # Matches failure
        assert len(registry.match({"event_type": "user.login", "status": "failure"})) == 1

    def test_any_status(self) -> None:
        """Watchers with status 'any' should match all events."""
        watchers = _make_watchers({
            "agent.activate": [{"plugin": "PCEStdout", "status": "any"}],
        })
        registry = WatcherRegistry(watchers)
        assert len(registry.match({"event_type": "agent.activate", "status": None})) == 1
        assert len(registry.match({"event_type": "agent.activate", "status": "success"})) == 1

    def test_match_fields_severity(self) -> None:
        """match_fields should allow filtering on any event field."""
        watchers = _make_watchers({
            ".*": [{"plugin": "PCEStdout", "status": "*",
                     "extra_data": {"match_fields": {"severity": "err"}}}],
        })
        registry = WatcherRegistry(watchers)
        # Matches err severity
        assert len(registry.match({
            "event_type": "request.authentication_failed",
            "status": "failure",
            "severity": "err",
        })) == 1
        # Does not match info severity
        assert len(registry.match({
            "event_type": "user.login",
            "status": "success",
            "severity": "info",
        })) == 0

    def test_match_fields_nested(self) -> None:
        """match_fields should support dot notation for nested fields."""
        watchers = _make_watchers({
            "user.*": [{"plugin": "PCESlack", "status": "*",
                         "extra_data": {"match_fields": {
                             "created_by.user.username": "admin@.*",
                         }}}],
        })
        registry = WatcherRegistry(watchers)
        assert len(registry.match({
            "event_type": "user.login",
            "status": "success",
            "created_by": {"user": {"username": "admin@illumio.com"}},
        })) == 1
        assert len(registry.match({
            "event_type": "user.login",
            "status": "success",
            "created_by": {"user": {"username": "other@illumio.com"}},
        })) == 0

    def test_match_fields_negation(self) -> None:
        """match_fields with ! prefix should negate the match."""
        watchers = _make_watchers({
            ".*": [{"plugin": "PCEStdout", "status": "*",
                     "extra_data": {"match_fields": {"severity": "!info"}}}],
        })
        registry = WatcherRegistry(watchers)
        # info should NOT match
        assert len(registry.match({
            "event_type": "user.login", "status": "success", "severity": "info",
        })) == 0
        # err SHOULD match
        assert len(registry.match({
            "event_type": "request.fail", "status": "failure", "severity": "err",
        })) == 1

    def test_match_fields_pipe_alternatives(self) -> None:
        """match_fields with pipe should match any of the alternatives."""
        watchers = _make_watchers({
            ".*": [{"plugin": "PCEStdout", "status": "*",
                     "extra_data": {"match_fields": {"severity": "err|warning"}}}],
        })
        registry = WatcherRegistry(watchers)
        assert len(registry.match({
            "event_type": "a", "status": None, "severity": "err",
        })) == 1
        assert len(registry.match({
            "event_type": "a", "status": None, "severity": "warning",
        })) == 1
        assert len(registry.match({
            "event_type": "a", "status": None, "severity": "info",
        })) == 0
