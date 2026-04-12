"""Tests for event enrichment: runbooks, workloads, policy diffs."""

from __future__ import annotations

from pretty_cool_events.enrichment import EventEnricher, ResourceCache, get_all_runbooks, get_runbook


class TestRunbooks:
    def test_exact_match(self) -> None:
        rb = get_runbook("agent.tampering")
        assert rb is not None
        assert rb["category"] == "agent-tampering"
        assert rb["severity_hint"] == "critical"
        assert "tampering" in rb["response"].lower()
        assert rb["url"].startswith("https://")

    def test_auth_failure(self) -> None:
        rb = get_runbook("request.authentication_failed")
        assert rb is not None
        assert rb["severity_hint"] == "critical"

    def test_policy_change(self) -> None:
        rb = get_runbook("rule_set.create")
        assert rb is not None
        assert rb["category"] == "policy-changes"

    def test_user_login(self) -> None:
        rb = get_runbook("user.login")
        assert rb is not None
        assert rb["category"] == "security-auth-activity"

    def test_unknown_event(self) -> None:
        rb = get_runbook("totally.made.up.event")
        assert rb is None

    def test_all_runbooks(self) -> None:
        all_rb = get_all_runbooks()
        assert len(all_rb) >= 10
        assert "agent-tampering" in all_rb
        assert "policy-changes" in all_rb


class TestResourceCache:
    def test_put_get(self) -> None:
        cache = ResourceCache(max_size=10, ttl=60)
        cache.put("key1", {"data": "value"})
        assert cache.get("key1") == {"data": "value"}

    def test_miss(self) -> None:
        cache = ResourceCache()
        assert cache.get("nonexistent") is None

    def test_max_size(self) -> None:
        cache = ResourceCache(max_size=3, ttl=60)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.put("d", 4)  # evicts oldest
        assert cache.size == 3

    def test_size(self) -> None:
        cache = ResourceCache()
        assert cache.size == 0
        cache.put("x", 1)
        assert cache.size == 1


class TestEventEnricher:
    def test_runbook_added(self) -> None:
        enricher = EventEnricher()
        event = {"event_type": "agent.tampering", "status": "success"}
        enricher.enrich(event)
        assert "_runbook" in event
        assert event["_runbook"]["category"] == "agent-tampering"

    def test_no_runbook_for_unknown(self) -> None:
        enricher = EventEnricher()
        event = {"event_type": "unknown.event", "status": "success"}
        enricher.enrich(event)
        assert "_runbook" not in event

    def test_policy_diff(self) -> None:
        enricher = EventEnricher()
        event = {
            "event_type": "rule_set.update",
            "status": "success",
            "resource_changes": [
                {
                    "change_type": "update",
                    "resource": {"rule_set": {"name": "Default", "href": "/orgs/1/rule_sets/1"}},
                    "changes": {
                        "enabled": {"before": True, "after": False},
                    },
                }
            ],
        }
        enricher.enrich(event)
        assert "_policy_diff" in event
        assert "enabled" in event["_policy_diff"]
        assert "True" in event["_policy_diff"]
        assert "False" in event["_policy_diff"]
        assert len(event["_policy_diff_lines"]) == 1

    def test_policy_diff_delete(self) -> None:
        enricher = EventEnricher()
        event = {
            "event_type": "rule_set.delete",
            "status": "success",
            "resource_changes": [
                {
                    "change_type": "delete",
                    "resource": {"rule_set": {"name": "OldRules", "href": "/orgs/1/rule_sets/99"}},
                    "changes": None,
                }
            ],
        }
        enricher.enrich(event)
        assert "_policy_diff" in event
        assert "DELETED" in event["_policy_diff"]
        assert "OldRules" in event["_policy_diff"]

    def test_no_enrichment_without_pce(self) -> None:
        """Without PCE client, workload enrichment is skipped but runbooks still work."""
        enricher = EventEnricher(pce_client=None)
        event = {"event_type": "agent.tampering", "status": "success"}
        enricher.enrich(event)
        assert "_runbook" in event
        assert "_workloads" not in event
