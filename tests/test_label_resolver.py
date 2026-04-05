"""Tests for the LabelResolver."""

from __future__ import annotations

from pretty_cool_events.label_resolver import LabelResolver

SAMPLE_LABELS = [
    {"key": "env", "value": "prod", "href": "/orgs/1/labels/1"},
    {"key": "env", "value": "dev", "href": "/orgs/1/labels/2"},
    {"key": "env", "value": "staging", "href": "/orgs/1/labels/3"},
    {"key": "app", "value": "payment", "href": "/orgs/1/labels/10"},
    {"key": "app", "value": "web", "href": "/orgs/1/labels/11"},
    {"key": "bu", "value": "banking", "href": "/orgs/1/labels/20"},
    {"key": "role", "value": "db", "href": "/orgs/1/labels/30"},
    {"key": "role", "value": "web", "href": "/orgs/1/labels/31"},
]


class TestLabelResolver:
    def _resolver(self) -> LabelResolver:
        r = LabelResolver()
        r.load(SAMPLE_LABELS)
        return r

    def test_resolve_single(self) -> None:
        r = self._resolver()
        assert r.resolve("env", "prod") == "/orgs/1/labels/1"
        assert r.resolve("env", "nonexistent") is None

    def test_label_keys(self) -> None:
        r = self._resolver()
        assert set(r.label_keys) == {"env", "app", "bu", "role"}

    def test_values_for_key(self) -> None:
        r = self._resolver()
        assert "prod" in r.values_for_key("env")
        assert "dev" in r.values_for_key("env")

    def test_parse_expression_and(self) -> None:
        """Comma = AND within one group."""
        r = self._resolver()
        result = r.parse_expression("env=prod, bu=banking")
        assert len(result) == 1  # one AND group
        assert len(result[0]) == 2  # two labels
        hrefs = {item["label"]["href"] for item in result[0]}
        assert hrefs == {"/orgs/1/labels/1", "/orgs/1/labels/20"}

    def test_parse_expression_or(self) -> None:
        """OR splits into separate groups."""
        r = self._resolver()
        result = r.parse_expression("role=db OR role=web")
        assert len(result) == 2  # two OR groups
        assert len(result[0]) == 1
        assert len(result[1]) == 1

    def test_parse_expression_empty(self) -> None:
        r = self._resolver()
        assert r.parse_expression("") == []

    def test_parse_exclude(self) -> None:
        r = self._resolver()
        result = r.parse_exclude("env=dev, env=staging")
        assert len(result) == 2
        hrefs = {item["label"]["href"] for item in result}
        assert hrefs == {"/orgs/1/labels/2", "/orgs/1/labels/3"}

    def test_parse_services(self) -> None:
        r = self._resolver()
        result = r.parse_services("443/tcp, 53/udp, 3306")
        assert len(result) == 3
        assert result[0] == {"port": 443, "proto": 6}
        assert result[1] == {"port": 53, "proto": 17}
        assert result[2] == {"port": 3306, "proto": 6}  # defaults to TCP

    def test_parse_services_empty(self) -> None:
        r = self._resolver()
        assert r.parse_services("") == []

    def test_unknown_label_skipped(self) -> None:
        """Unknown labels in expressions should be skipped with a warning."""
        r = self._resolver()
        result = r.parse_expression("env=prod, env=NONEXISTENT")
        assert len(result) == 1
        assert len(result[0]) == 1  # only prod resolved
