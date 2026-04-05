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

    def test_api_render_template(self, client: FlaskClient) -> None:
        """POST /api/render renders an event through a template."""
        response = client.post("/api/render", json={
            "event": {
                "event_type": "user.login",
                "status": "success",
                "severity": "info",
                "timestamp": "2026-01-01T00:00:00Z",
                "pce_fqdn": "test.example.com",
                "href": "/orgs/1/events/test",
                "created_by": {"user": {"username": "admin"}},
            },
            "template": "default.html",
        })
        assert response.status_code == 200
        data = response.get_json()
        assert "rendered" in data
        assert "user.login" in data["rendered"]
        assert data["template"] == "default.html"

    def test_api_render_template_email_full(self, client: FlaskClient) -> None:
        """email-full.html renders with all sections."""
        response = client.post("/api/render", json={
            "event": {
                "event_type": "rule_set.create",
                "status": "success",
                "severity": "info",
                "timestamp": "2026-01-01T00:00:00Z",
                "pce_fqdn": "pce.example.com",
                "href": "/orgs/1/events/123",
                "created_by": {"user": {"username": "admin@example.com"}},
                "action": {"api_endpoint": "/api/v2/orgs/1/rule_sets", "api_method": "POST",
                           "http_status_code": 201, "src_ip": "10.0.0.1"},
                "resource_changes": [],
                "notifications": [],
            },
            "template": "email-full.html",
        })
        assert response.status_code == 200
        data = response.get_json()
        assert "rule_set.create" in data["rendered"]
        assert "admin@example.com" in data["rendered"]
        assert "API Action" in data["rendered"]

    def test_api_render_bad_template(self, client: FlaskClient) -> None:
        response = client.post("/api/render", json={
            "event": {"event_type": "test"},
            "template": "nonexistent.html",
        })
        assert response.status_code == 400

    def test_api_list_templates(self, client: FlaskClient) -> None:
        response = client.get("/api/templates")
        assert response.status_code == 200
        templates = response.get_json()
        assert isinstance(templates, list)
        assert "default.html" in templates
        assert "email-full.html" in templates
        assert "_macros.html" not in templates

    # --- Config persistence ---

    def test_config_post_persists(self, flask_app: Flask, client: FlaskClient, tmp_path: Any) -> None:
        """POST to /config should persist changes to disk."""
        config = flask_app.config["APP_CONFIG"]
        config_file = tmp_path / "config.yaml"
        # Write initial config
        from pretty_cool_events.config import save_config
        save_config(config, config_file, backup=False)
        config.config_path = str(config_file)

        client.post("/config", data={
            "pce": "new-pce.example.com",
            "pce_api_user": config.pce.pce_api_user,
            "pce_org": "1",
            "pce_poll_interval": "30",
        }, follow_redirects=True)

        # Verify persisted
        from pretty_cool_events.config import load_config
        reloaded = load_config(config_file)
        assert reloaded.pce.pce == "new-pce.example.com"
        assert reloaded.pce.pce_poll_interval == 30

    def test_watcher_persists(self, flask_app: Flask, client: FlaskClient, tmp_path: Any) -> None:
        """Adding a watcher should persist to disk."""
        config = flask_app.config["APP_CONFIG"]
        config_file = tmp_path / "config.yaml"
        from pretty_cool_events.config import save_config
        save_config(config, config_file, backup=False)
        config.config_path = str(config_file)

        client.post("/watchers", data={
            "watcher_pattern[]": "agent.tampering",
            "watcher_status[]": "success",
            "watcher_plugin[]": "PCEStdout",
            "watcher_severity[]": "info",
            "watcher_template[]": "default.html",
        }, follow_redirects=True)

        from pretty_cool_events.config import load_config
        reloaded = load_config(config_file)
        assert "agent.tampering" in reloaded.watchers

    # --- Authentication ---

    def test_no_auth_when_not_configured(self, client: FlaskClient) -> None:
        """Without auth config, all pages accessible."""
        response = client.get("/")
        assert response.status_code == 200

    def test_auth_redirects_to_login(self, flask_app: Flask, client: FlaskClient) -> None:
        """With auth configured, unauthenticated requests redirect to login."""
        config = flask_app.config["APP_CONFIG"]
        config.httpd.username = "admin"
        config.httpd.password = "secret"

        response = client.get("/")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_login_success(self, flask_app: Flask, client: FlaskClient) -> None:
        """Correct credentials grant access."""
        config = flask_app.config["APP_CONFIG"]
        config.httpd.username = "admin"
        config.httpd.password = "secret"

        response = client.post("/login", data={"username": "admin", "password": "secret"},
                               follow_redirects=True)
        assert response.status_code == 200
        assert b"Pretty Cool Events" in response.data

    def test_login_failure(self, flask_app: Flask, client: FlaskClient) -> None:
        """Wrong credentials show error."""
        config = flask_app.config["APP_CONFIG"]
        config.httpd.username = "admin"
        config.httpd.password = "secret"

        response = client.post("/login", data={"username": "admin", "password": "wrong"},
                               follow_redirects=True)
        assert b"Invalid" in response.data

    def test_logout(self, flask_app: Flask, client: FlaskClient) -> None:
        """Logout clears the session."""
        config = flask_app.config["APP_CONFIG"]
        config.httpd.username = "admin"
        config.httpd.password = "secret"

        # Login
        client.post("/login", data={"username": "admin", "password": "secret"})
        # Verify access
        assert client.get("/").status_code == 200
        # Logout
        client.get("/logout")
        # Verify redirected
        assert client.get("/").status_code == 302

    # --- SSE ---

    def test_sse_endpoint(self, client: FlaskClient) -> None:
        """SSE endpoint returns event-stream content type."""
        response = client.get("/api/stream")
        assert response.content_type.startswith("text/event-stream")
