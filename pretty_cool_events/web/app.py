"""Flask application factory."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from flask import Flask

from pretty_cool_events.config import AppConfig
from pretty_cool_events.pce_client import PCEClient
from pretty_cool_events.plugins.base import OutputPlugin
from pretty_cool_events.stats import StatsTracker
from pretty_cool_events.throttle import Throttler


def create_app(
    config: AppConfig,
    stats: StatsTracker,
    plugins: dict[str, OutputPlugin],
    pce_client: PCEClient | None = None,
    throttler: Throttler | None = None,
    service_manager: Any = None,
) -> Flask:
    """Create and configure the Flask application."""
    template_dir = str(Path(__file__).parent / "templates")
    static_dir = str(Path(__file__).parent / "static")

    app = Flask(
        "pretty-cool-events",
        template_folder=template_dir,
        static_folder=static_dir,
    )
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    @app.after_request
    def _set_security_headers(response: Any) -> Any:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    def split_filter(value: str, delimiter: str | None = None) -> list[str]:
        return value.split(delimiter)

    def json_filter(value: Any) -> str:
        return json.dumps(value, indent=4, sort_keys=True, ensure_ascii=True)

    app.jinja_env.filters["split"] = split_filter
    app.jinja_env.filters["json_filter"] = json_filter

    # Store shared state on the app
    app.config["APP_CONFIG"] = config
    app.config["STATS"] = stats
    app.config["PLUGINS"] = plugins
    app.config["PCE_CLIENT"] = pce_client
    app.config["THROTTLER"] = throttler
    app.config["SERVICE_MANAGER"] = service_manager

    from pretty_cool_events.web.routes import bp
    app.register_blueprint(bp)

    return app
