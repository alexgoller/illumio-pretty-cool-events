"""Web UI routes."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from pretty_cool_events.config import AppConfig, WatcherAction, load_event_types
from pretty_cool_events.plugin_meta import PLUGIN_METADATA

logger = logging.getLogger(__name__)

bp = Blueprint("main", __name__)


def _get_config() -> AppConfig:
    return current_app.config["APP_CONFIG"]


def _get_stats() -> Any:
    return current_app.config["STATS"]


def _get_pce_client() -> Any:
    return current_app.config.get("PCE_CLIENT")


@bp.route("/")
def index() -> str:
    stats = _get_stats()
    config = _get_config()
    return render_template("index.html", stats=stats.snapshot(), config=config)


@bp.route("/statistics")
def statistics() -> str:
    stats = _get_stats().snapshot()
    return render_template(
        "statistics.html",
        stats=stats,
        event_stats_json=json.dumps(stats["event_stats"]),
        plugin_stats_json=json.dumps(stats["plugin_stats"]),
        event_timeline_json=json.dumps(stats.get("event_timeline", [])),
    )


@bp.route("/events")
def events_page() -> str:
    """Event explorer - browse historical PCE events with filtering."""
    return render_template("events.html", event_types=load_event_types(), config=_get_config())


@bp.route("/plugins", methods=["GET", "POST"])
def plugins_page() -> str:
    """Plugin configuration with enable/disable toggles and full settings."""
    config = _get_config()

    if request.method == "POST":
        enabled = set(request.form.getlist("enabled_plugins"))

        # Build new plugin_config: only keep enabled plugins, update their settings
        new_plugin_config: dict[str, dict[str, Any]] = {}
        for plugin_name, meta in PLUGIN_METADATA.items():
            if plugin_name not in enabled:
                continue
            plugin_cfg: dict[str, Any] = {}
            for field_name in meta.fields:
                form_key = f"plugin[{plugin_name}][{field_name}]"
                val = request.form.get(form_key, "")
                # Preserve existing secret values if the form sends empty
                if meta.fields[field_name].secret and not val:
                    val = (config.plugin_config.get(plugin_name) or {}).get(field_name, "")
                # Convert numeric fields
                if meta.fields[field_name].field_type == "number" and val:
                    try:
                        plugin_cfg[field_name] = int(val)
                    except ValueError:
                        plugin_cfg[field_name] = val
                else:
                    plugin_cfg[field_name] = val
            new_plugin_config[plugin_name] = plugin_cfg

        config.plugin_config = new_plugin_config
        flash("Plugin configuration saved", "success")
        return redirect(url_for("main.plugins_page"))

    # Build context for the template
    enabled_plugins = set(config.plugin_config.keys())
    plugin_configs = {name: (config.plugin_config.get(name) or {}) for name in PLUGIN_METADATA}

    return render_template(
        "plugins.html",
        all_plugins=PLUGIN_METADATA,
        enabled_plugins=enabled_plugins,
        plugin_configs=plugin_configs,
    )


@bp.route("/guide")
def guide_page() -> str:
    """How-it-works guide and documentation."""
    return render_template("guide.html", event_types=load_event_types())


@bp.route("/api/events")
def api_events() -> Any:
    """Fetch events from the PCE with time range and field filtering.

    Query params:
        since: ISO timestamp or relative like "1h", "24h", "7d", "30d"
        until: ISO timestamp (default: now)
        max_results: max events to return (default: 500)
        event_type: filter by event_type (supports regex)
        status: filter by status (success, failure, null, or * for all)
        severity: filter by severity
        search: free-text search across all string fields
        created_by: filter by creator type (user, system, agent)
        username: filter by created_by.user.username
    """
    pce_client = _get_pce_client()
    if not pce_client:
        return jsonify({"error": "PCE client not available"}), 503

    # Parse time range
    since_param = request.args.get("since", "24h")
    until_param = request.args.get("until")
    max_results = int(request.args.get("max_results", "500"))

    now = datetime.now(timezone.utc)
    since = _parse_time(since_param, now)
    until = _parse_time(until_param, now) if until_param else now

    # Fetch from PCE
    events = pce_client.get_events(since=since, until=until, max_results=max_results)

    # Apply client-side filters
    event_type_filter = request.args.get("event_type", "")
    status_filter = request.args.get("status", "")
    severity_filter = request.args.get("severity", "")
    search_filter = request.args.get("search", "")
    created_by_filter = request.args.get("created_by", "")
    username_filter = request.args.get("username", "")

    filtered = _apply_filters(
        events,
        event_type=event_type_filter,
        status=status_filter,
        severity=severity_filter,
        search=search_filter,
        created_by=created_by_filter,
        username=username_filter,
    )

    return jsonify({
        "events": filtered,
        "total_fetched": len(events),
        "total_filtered": len(filtered),
        "since": since.isoformat() if since else None,
        "until": until.isoformat(),
    })


def _parse_time(value: str | None, now: datetime) -> datetime | None:
    """Parse a time value that can be relative (1h, 24h, 7d) or ISO format."""
    if not value:
        return None

    # Relative time
    match = re.match(r"^(\d+)([mhdw])$", value.strip())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        deltas = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount),
                  "d": timedelta(days=amount), "w": timedelta(weeks=amount)}
        return now - deltas[unit]

    # ISO timestamp
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _apply_filters(
    events: list[dict[str, Any]],
    event_type: str = "",
    status: str = "",
    severity: str = "",
    search: str = "",
    created_by: str = "",
    username: str = "",
) -> list[dict[str, Any]]:
    """Apply client-side filters to a list of events."""
    result = events

    if event_type:
        try:
            pattern = re.compile(event_type, re.IGNORECASE)
            result = [e for e in result if pattern.search(e.get("event_type", ""))]
        except re.error:
            result = [e for e in result if event_type in e.get("event_type", "")]

    if status and status != "*":
        if status == "null":
            result = [e for e in result if e.get("status") is None]
        else:
            result = [e for e in result if e.get("status") == status]

    if severity:
        result = [e for e in result if e.get("severity") == severity]

    if created_by:
        result = [e for e in result if created_by in (e.get("created_by") or {})]

    if username:
        username_lower = username.lower()
        result = [
            e for e in result
            if username_lower in (
                (e.get("created_by") or {}).get("user", {}).get("username", "")
            ).lower()
        ]

    if search:
        search_lower = search.lower()
        result = [e for e in result if _event_contains(e, search_lower)]

    return result


def _event_contains(event: dict[str, Any], search: str) -> bool:
    """Deep search: check if any string value in the event contains the search term."""
    def _search(obj: Any) -> bool:
        if isinstance(obj, str):
            return search in obj.lower()
        if isinstance(obj, dict):
            return any(_search(v) for v in obj.values())
        if isinstance(obj, list):
            return any(_search(item) for item in obj)
        return False
    return _search(event)


@bp.route("/config", methods=["GET", "POST"])
def config_page() -> str:
    config = _get_config()

    if request.method == "POST":
        for key in ["pce", "pce_api_user", "pce_org", "pce_poll_interval"]:
            val = request.form.get(key)
            if val is not None:
                if key == "pce_org" or key == "pce_poll_interval":
                    setattr(config.pce, key, int(val))
                else:
                    setattr(config.pce, key, val)

        config.httpd.enabled = "httpd" in request.form
        config.traffic_worker = "traffic_worker" in request.form

        for plugin_name, plugin_config in config.plugin_config.items():
            if plugin_config is None:
                continue
            for key in plugin_config:
                form_key = f"plugin_config[{plugin_name}][{key}]"
                if form_key in request.form:
                    config.plugin_config[plugin_name][key] = request.form[form_key]

        flash("Configuration updated successfully", "success")
        return redirect(url_for("main.config_page"))

    return render_template("config.html", config=config)


@bp.route("/watchers", methods=["GET", "POST"])
def watchers_page() -> str:
    config = _get_config()
    event_types = load_event_types()

    if request.method == "POST":
        patterns = request.form.getlist("watcher_pattern[]")
        statuses = request.form.getlist("watcher_status[]")
        plugins = request.form.getlist("watcher_plugin[]")
        severities = request.form.getlist("watcher_severity[]")
        templates = request.form.getlist("watcher_template[]")

        for i, pattern in enumerate(patterns):
            if not pattern:
                continue

            action = WatcherAction(
                status=statuses[i] if i < len(statuses) else "success",
                severity=severities[i] if i < len(severities) else "info",
                plugin=plugins[i] if i < len(plugins) else "PCEStdout",
                extra_data={"template": templates[i] if i < len(templates) else "default.html"},
            )

            if pattern in config.watchers:
                config.watchers[pattern].append(action)
            else:
                config.watchers[pattern] = [action]

        flash("Watcher configuration updated", "success")
        return redirect(url_for("main.watchers_page"))

    return render_template(
        "watchers.html",
        config=config,
        watchers=config.watchers,
        event_types=event_types,
    )


@bp.route("/watchers/delete", methods=["POST"])
def delete_watcher() -> str:
    config = _get_config()
    pattern = request.form.get("pattern", "")
    index = request.form.get("index")

    if pattern in config.watchers and index is not None:
        idx = int(index)
        if 0 <= idx < len(config.watchers[pattern]):
            config.watchers[pattern].pop(idx)
            if not config.watchers[pattern]:
                del config.watchers[pattern]
            flash(f"Watcher removed: {pattern}", "success")

    return redirect(url_for("main.watchers_page"))


@bp.route("/api/watchers", methods=["POST"])
def api_create_watcher() -> Any:
    """Create a watcher from JSON. Used by the event explorer's 'Create Watcher' flow."""
    config = _get_config()
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    pattern = data.get("pattern", "")
    if not pattern:
        return jsonify({"error": "pattern is required"}), 400

    extra_data: dict[str, Any] = {}
    if data.get("template"):
        extra_data["template"] = data["template"]
    if data.get("match_fields"):
        extra_data["match_fields"] = data["match_fields"]
    # Pass through any extra keys (channel, email_to, phone_number, etc.)
    for key in ("channel", "email_to", "phone_number"):
        if data.get(key):
            extra_data[key] = data[key]

    action = WatcherAction(
        status=data.get("status", "*"),
        severity=data.get("severity", "info"),
        plugin=data.get("plugin", "PCEStdout"),
        extra_data=extra_data,
    )

    if pattern in config.watchers:
        config.watchers[pattern].append(action)
    else:
        config.watchers[pattern] = [action]

    logger.info("Watcher created via API: %s -> %s", pattern, action.plugin)
    return jsonify({"ok": True, "pattern": pattern, "plugin": action.plugin})


@bp.route("/api/render", methods=["POST"])
def api_render_template() -> Any:
    """Render an event through a template. Returns the rendered output."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    event_data = data.get("event")
    template_name = data.get("template", "default.html")
    if not event_data:
        return jsonify({"error": "event is required"}), 400

    config = _get_config()
    template_globals = {
        "pce_fqdn": config.pce.pce,
        "pce_org": config.pce.pce_org,
    }

    import importlib.resources

    from jinja2 import Environment, FileSystemLoader, select_autoescape

    template_dir = str(importlib.resources.files("pretty_cool_events") / "templates")
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["json_filter"] = lambda v: __import__("json").dumps(
        v, indent=4, sort_keys=True, ensure_ascii=True
    )

    try:
        tmpl = env.get_template(template_name)
        context: dict[str, Any] = {}
        context.update(template_globals)
        context.update(event_data)
        context["event"] = event_data
        rendered = tmpl.render(**context)
        return jsonify({"rendered": rendered, "template": template_name})
    except Exception as e:
        return jsonify({"error": str(e), "template": template_name}), 400


@bp.route("/api/templates")
def api_list_templates() -> Any:
    """List available output templates."""
    import importlib.resources

    template_dir = importlib.resources.files("pretty_cool_events") / "templates"
    templates = []
    for item in template_dir.iterdir():
        name = item.name
        if name.startswith("_"):
            continue
        templates.append(name)
    return jsonify(sorted(templates))


@bp.route("/api/stats")
def api_stats() -> Any:
    return jsonify(_get_stats().snapshot())


@bp.route("/api/health")
def api_health() -> Any:
    return jsonify({"status": "ok"})
