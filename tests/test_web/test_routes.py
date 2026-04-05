"""Tests for the Flask web UI routes."""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient

from pretty_cool_events.config import AppConfig
from pretty_cool_events.stats import StatsTracker
from pretty_cool_events.web.app import create_app


@pytest.fixture()
def flask_app(sample_config: AppConfig) -> Flask:
    """Create a Flask app using the app factory with test configuration."""
    stats = StatsTracker()
    stats.record_event("user.login")
    app = create_app(sample_config, stats, {})
    app.config["TESTING"] = True
    return app


@pytest.fixture()
def client(flask_app: Flask) -> FlaskClient:
    return flask_app.test_client()


class TestWebRoutes:
    def test_index_page(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert b"Pretty Cool Events" in response.data

    def test_statistics_page(self, client: FlaskClient) -> None:
        response = client.get("/statistics")
        assert response.status_code == 200

    def test_config_page(self, client: FlaskClient) -> None:
        response = client.get("/config")
        assert response.status_code == 200

    def test_watchers_page(self, client: FlaskClient) -> None:
        response = client.get("/watchers")
        assert response.status_code == 200

    def test_api_stats(self, client: FlaskClient) -> None:
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.get_json()
        assert "events_received" in data
        assert data["events_received"] == 1

    def test_api_health(self, client: FlaskClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data == {"status": "ok"}

    def test_events_page(self, client: FlaskClient) -> None:
        response = client.get("/events")
        assert response.status_code == 200
        assert b"Event Explorer" in response.data

    def test_api_events_no_client(self, client: FlaskClient) -> None:
        """API returns 503 when PCE client is not available."""
        response = client.get("/api/events?since=1h")
        assert response.status_code == 503
        data = response.get_json()
        assert "error" in data

    def test_plugins_page(self, client: FlaskClient) -> None:
        response = client.get("/plugins")
        assert response.status_code == 200
        assert b"Console Output" in response.data  # PCEStdout display name
        assert b"Slack" in response.data

    def test_plugins_page_shows_descriptions(self, client: FlaskClient) -> None:
        response = client.get("/plugins")
        assert b"How it works" in response.data
        assert b"Prints event notifications" in response.data  # PCEStdout description

    def test_plugins_enable_disable(self, client: FlaskClient) -> None:
        """POST to plugins page should update enabled plugins."""
        response = client.post("/plugins", data={
            "enabled_plugins": ["PCEStdout", "PCEFile"],
            "plugin[PCEStdout][prepend]": "[TEST] ",
            "plugin[PCEFile][logfile]": "test.log",
            "plugin[PCEFile][template]": "default.html",
        }, follow_redirects=True)
        assert response.status_code == 200
        assert b"Plugin configuration saved" in response.data

    def test_guide_page(self, client: FlaskClient) -> None:
        response = client.get("/guide")
        assert response.status_code == 200
        assert b"How It Works" in response.data
        assert b"Getting Started" in response.data
        assert b"Watcher Matching" in response.data

    def test_api_create_watcher(self, flask_app: Flask, client: FlaskClient) -> None:
        """POST /api/watchers creates a watcher from JSON."""
        response = client.post("/api/watchers", json={
            "pattern": "user.login",
            "status": "success",
            "plugin": "PCEStdout",
            "template": "default.html",
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data["ok"] is True
        assert data["pattern"] == "user.login"
        # Verify it was actually added to config
        config = flask_app.config["APP_CONFIG"]
        assert "user.login" in config.watchers
        assert config.watchers["user.login"][-1].plugin == "PCEStdout"

    def test_api_create_watcher_with_match_fields(self, flask_app: Flask, client: FlaskClient) -> None:
        """POST /api/watchers with match_fields creates an advanced watcher."""
        response = client.post("/api/watchers", json={
            "pattern": ".*",
            "status": "*",
            "plugin": "PCEStdout",
            "template": "default.html",
            "match_fields": {"severity": "err|warning"},
        })
        assert response.status_code == 200
        config = flask_app.config["APP_CONFIG"]
        last_action = config.watchers[".*"][-1]
        assert last_action.extra_data["match_fields"]["severity"] == "err|warning"

    def test_api_create_watcher_missing_pattern(self, client: FlaskClient) -> None:
        response = client.post("/api/watchers", json={"plugin": "PCEStdout"})
        assert response.status_code == 400
