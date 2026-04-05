"""Tests for the event throttler."""

from __future__ import annotations

import time
from unittest.mock import patch

from pretty_cool_events.throttle import Throttler, parse_throttle


class TestParseThrottle:
    def test_valid_specs(self) -> None:
        assert parse_throttle("1/1h") == (1, 3600)
        assert parse_throttle("5/1h") == (5, 3600)
        assert parse_throttle("10/24h") == (10, 86400)
        assert parse_throttle("1/30m") == (1, 1800)
        assert parse_throttle("100/7d") == (100, 604800)

    def test_empty(self) -> None:
        assert parse_throttle("") is None
        assert parse_throttle("  ") is None

    def test_invalid(self) -> None:
        assert parse_throttle("invalid") is None
        assert parse_throttle("abc/1h") is None


class TestThrottler:
    def test_no_throttle(self) -> None:
        """Without a default, everything is allowed."""
        t = Throttler("")
        for _ in range(100):
            assert t.allow("user.login", "PCESlack")

    def test_default_throttle(self) -> None:
        """Default throttle limits dispatch count."""
        t = Throttler("2/1h")
        assert t.allow("user.login", "PCESlack")
        assert t.allow("user.login", "PCESlack")
        assert not t.allow("user.login", "PCESlack")  # 3rd blocked

    def test_different_keys_independent(self) -> None:
        """Different event types are tracked independently."""
        t = Throttler("1/1h")
        assert t.allow("user.login", "PCESlack")
        assert not t.allow("user.login", "PCESlack")  # blocked
        assert t.allow("user.logout", "PCESlack")  # different type = ok

    def test_different_plugins_independent(self) -> None:
        """Same event to different plugins are tracked independently."""
        t = Throttler("1/1h")
        assert t.allow("user.login", "PCESlack")
        assert t.allow("user.login", "PCEMail")  # different plugin = ok

    def test_per_watcher_override(self) -> None:
        """Per-watcher throttle overrides the default."""
        t = Throttler("1/1h")
        assert t.allow("user.login", "PCESlack")
        assert not t.allow("user.login", "PCESlack")  # default blocks
        # But with a higher override:
        t2 = Throttler("1/1h")
        assert t2.allow("user.login", "PCEFile", override_spec="10/1h")
        assert t2.allow("user.login", "PCEFile", override_spec="10/1h")
        assert t2.allow("user.login", "PCEFile", override_spec="10/1h")  # still ok

    def test_zero_suppresses_all(self) -> None:
        """0/1h = mute all notifications."""
        t = Throttler("0/1h")
        assert not t.allow("user.login", "PCESlack")

    def test_suppressed_count(self) -> None:
        t = Throttler("1/1h")
        t.allow("user.login", "PCESlack")
        t.allow("user.login", "PCESlack")  # suppressed
        t.allow("user.login", "PCESlack")  # suppressed
        assert t.suppressed_count("user.login", "PCESlack") == 2

    def test_snapshot(self) -> None:
        t = Throttler("1/1h")
        t.allow("user.login", "PCESlack")
        t.allow("user.login", "PCESlack")
        snap = t.snapshot()
        assert snap["default"] == "1/1h"
        assert snap["total_suppressed"] == 1
        assert snap["active_keys"] == 1

    def test_window_expiry(self) -> None:
        """Events should be allowed again after the window expires."""
        t = Throttler("1/1h")
        # Mock time.monotonic to simulate time passing
        base = time.monotonic()
        with patch("pretty_cool_events.throttle.time") as mock_time:
            mock_time.monotonic.return_value = base
            assert t.allow("user.login", "PCESlack")
            assert not t.allow("user.login", "PCESlack")

            # Fast forward past the window
            mock_time.monotonic.return_value = base + 3601
            assert t.allow("user.login", "PCESlack")  # allowed again

    def test_update_default(self) -> None:
        t = Throttler("")
        assert t.allow("a", "b")
        t.update_default("1/1h")
        assert t.allow("a", "b")
        assert not t.allow("a", "b")

    def test_reset(self) -> None:
        t = Throttler("1/1h")
        t.allow("a", "b")
        t.allow("a", "b")
        assert t.snapshot()["total_suppressed"] == 1
        t.reset()
        assert t.snapshot()["total_suppressed"] == 0
        assert t.allow("a", "b")  # allowed again after reset
