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


def create_app(
    config: AppConfig,
    stats: StatsTracker,
    plugins: dict[str, OutputPlugin],
    pce_client: PCEClient | None = None,
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

    from pretty_cool_events.web.routes import bp
    app.register_blueprint(bp)

    return app
