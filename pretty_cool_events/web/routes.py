"""Web UI routes with authentication, config persistence, and SSE."""

from __future__ import annotations

import functools
import importlib.resources
import json
import logging
import queue
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from jinja2 import Environment, FileSystemLoader, select_autoescape

from pretty_cool_events.config import (
    AppConfig,
    TrafficWatcher,
    WatcherAction,
    load_event_types,
    save_config,
)
from pretty_cool_events.label_resolver import LabelResolver
from pretty_cool_events.plugin_meta import PLUGIN_METADATA

logger = logging.getLogger(__name__)

bp = Blueprint("main", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_config() -> AppConfig:
    return current_app.config["APP_CONFIG"]


def _get_stats() -> Any:
    return current_app.config["STATS"]


def _get_pce_client() -> Any:
    return current_app.config.get("PCE_CLIENT")


def _get_label_resolver() -> LabelResolver:
    """Get or lazily initialize the label resolver with PCE labels."""
    resolver = current_app.config.get("LABEL_RESOLVER")
    if resolver is None:
        resolver = LabelResolver()
        current_app.config["LABEL_RESOLVER"] = resolver
    # Refresh if empty (first call or after PCE reconnect)
    if not resolver.label_keys:
        pce = _get_pce_client()
        if pce:
            labels = pce.get_labels()
            resolver.load(labels)
            logger.info("Loaded %d labels (%d keys)", len(labels), len(resolver.label_keys))
    return resolver


def _persist_config() -> None:
    """Save current config to disk if a config_path is known."""
    config = _get_config()
    if config.config_path:
        try:
            save_config(config, config.config_path)
            logger.info("Config persisted to %s", config.config_path)
        except Exception:
            logger.exception("Failed to persist config to %s", config.config_path)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def _auth_required(f: Any) -> Any:
    """Decorator: require login if httpd username/password are configured."""
    @functools.wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        config = _get_config()
        if config.httpd.username and config.httpd.password and not session.get("authenticated"):
            return redirect(url_for("main.login_page", next=request.path))
        return f(*args, **kwargs)
    return decorated


@bp.route("/login", methods=["GET", "POST"])
def login_page() -> Any:
    config = _get_config()
    if not (config.httpd.username and config.httpd.password):
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == config.httpd.username and password == config.httpd.password:
            session["authenticated"] = True
            next_url = request.args.get("next", "/")
            return redirect(next_url)
        flash("Invalid username or password", "danger")

    return render_template("login.html")


@bp.route("/logout")
def logout_page() -> Any:
    session.pop("authenticated", None)
    flash("Logged out", "success")
    return redirect(url_for("main.login_page"))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route("/")
@_auth_required
def index() -> str:
    stats = _get_stats()
    config = _get_config()
    return render_template("index.html", stats=stats.snapshot(), config=config)


@bp.route("/statistics")
@_auth_required
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
@_auth_required
def events_page() -> str:
    return render_template("events.html", event_types=load_event_types(), config=_get_config())


@bp.route("/plugins", methods=["GET", "POST"])
@_auth_required
def plugins_page() -> str:
    config = _get_config()

    if request.method == "POST":
        enabled = set(request.form.getlist("enabled_plugins"))
        new_plugin_config: dict[str, dict[str, Any]] = {}
        for plugin_name, meta in PLUGIN_METADATA.items():
            if plugin_name not in enabled:
                continue
            plugin_cfg: dict[str, Any] = {}
            for field_name in meta.fields:
                form_key = f"plugin[{plugin_name}][{field_name}]"
                val = request.form.get(form_key, "")
                if meta.fields[field_name].secret and not val:
                    val = (config.plugin_config.get(plugin_name) or {}).get(field_name, "")
                if meta.fields[field_name].field_type == "number" and val:
                    try:
                        plugin_cfg[field_name] = int(val)
                    except ValueError:
                        plugin_cfg[field_name] = val
                else:
                    plugin_cfg[field_name] = val
            new_plugin_config[plugin_name] = plugin_cfg

        config.plugin_config = new_plugin_config
        _persist_config()
        flash("Plugin configuration saved", "success")
        return redirect(url_for("main.plugins_page"))

    enabled_plugins = set(config.plugin_config.keys())
    plugin_configs = {name: (config.plugin_config.get(name) or {}) for name in PLUGIN_METADATA}
    return render_template(
        "plugins.html",
        all_plugins=PLUGIN_METADATA,
        enabled_plugins=enabled_plugins,
        plugin_configs=plugin_configs,
    )


@bp.route("/diagram")
@_auth_required
def diagram_page() -> str:
    """Visual watcher flow diagram."""
    config = _get_config()
    meta_map = {k: {"display_name": v.display_name, "icon": v.icon}
                for k, v in PLUGIN_METADATA.items()}
    return render_template(
        "diagram.html",
        watchers_json=json.dumps(
            {p: [a.model_dump() for a in actions] for p, actions in config.watchers.items()},
            default=str,
        ),
        traffic_watchers_json=json.dumps(
            [tw.model_dump() for tw in config.traffic_watchers],
            default=str,
        ),
        plugin_meta_json=json.dumps(meta_map),
        config=config,
    )


@bp.route("/guide")
@_auth_required
def guide_page() -> str:
    return render_template("guide.html", event_types=load_event_types())


@bp.route("/config", methods=["GET", "POST"])
@_auth_required
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

        # Auth settings
        new_user = request.form.get("httpd_username", "")
        new_pass = request.form.get("httpd_password", "")
        config.httpd.username = new_user
        if new_pass:  # Only update password if provided (don't blank it on empty form)
            config.httpd.password = new_pass

        _persist_config()
        flash("Configuration saved", "success")
        return redirect(url_for("main.config_page"))

    return render_template("config.html", config=config)


@bp.route("/watchers", methods=["GET", "POST"])
@_auth_required
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

        _persist_config()
        flash("Watcher configuration saved", "success")
        return redirect(url_for("main.watchers_page"))

    return render_template(
        "watchers.html", config=config, watchers=config.watchers, event_types=event_types,
    )


@bp.route("/watchers/delete", methods=["POST"])
@_auth_required
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
            _persist_config()
            flash(f"Watcher removed: {pattern}", "success")

    return redirect(url_for("main.watchers_page"))


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@bp.route("/api/events")
@_auth_required
def api_events() -> Any:
    pce_client = _get_pce_client()
    if not pce_client:
        return jsonify({"error": "PCE client not available"}), 503

    since_param = request.args.get("since", "24h")
    until_param = request.args.get("until")
    max_results = int(request.args.get("max_results", "500"))

    now = datetime.now(timezone.utc)
    since = _parse_time(since_param, now)
    until = _parse_time(until_param, now) if until_param else now

    events = pce_client.get_events(since=since, until=until, max_results=max_results)

    filtered = _apply_filters(
        events,
        event_type=request.args.get("event_type", ""),
        status=request.args.get("status", ""),
        severity=request.args.get("severity", ""),
        search=request.args.get("search", ""),
        created_by=request.args.get("created_by", ""),
        username=request.args.get("username", ""),
    )

    return jsonify({
        "events": filtered,
        "total_fetched": len(events),
        "total_filtered": len(filtered),
        "since": since.isoformat() if since else None,
        "until": until.isoformat(),
    })


@bp.route("/api/watchers", methods=["POST"])
@_auth_required
def api_create_watcher() -> Any:
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

    _persist_config()
    logger.info("Watcher created via API: %s -> %s", pattern, action.plugin)
    return jsonify({"ok": True, "pattern": pattern, "plugin": action.plugin})


@bp.route("/traffic")
@_auth_required
def traffic_page() -> str:
    """Traffic flow explorer with label-based querying."""
    resolver = _get_label_resolver()
    return render_template(
        "traffic.html",
        label_keys=resolver.label_keys,
        labels_json=json.dumps(resolver.all_labels()),
        config=_get_config(),
    )


@bp.route("/api/traffic/labels")
@_auth_required
def api_traffic_labels() -> Any:
    """Return all labels grouped by key for the traffic query builder."""
    resolver = _get_label_resolver()
    grouped: dict[str, list[str]] = {}
    for label in resolver.all_labels():
        grouped.setdefault(label["key"], []).append(label["value"])
    return jsonify(grouped)


@bp.route("/api/traffic/query", methods=["POST"])
@_auth_required
def api_traffic_query() -> Any:
    """Create an async traffic query from human-readable label expressions."""
    pce = _get_pce_client()
    if not pce:
        return jsonify({"error": "PCE client not available"}), 503

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    resolver = _get_label_resolver()

    # Parse time range
    now = datetime.now(timezone.utc)
    since = _parse_time(data.get("since", "24h"), now) or (now - timedelta(days=1))
    until = _parse_time(data.get("until"), now) or now

    # Parse label expressions into PCE format
    src_include = resolver.parse_expression(data.get("src_include", ""))
    src_exclude = resolver.parse_exclude(data.get("src_exclude", ""))
    dst_include = resolver.parse_expression(data.get("dst_include", ""))
    dst_exclude = resolver.parse_exclude(data.get("dst_exclude", ""))
    svc_include = resolver.parse_services(data.get("services_include", ""))
    svc_exclude = resolver.parse_services(data.get("services_exclude", ""))

    policy_decisions = data.get("policy_decisions", ["allowed", "blocked", "potentially_blocked"])
    max_results = int(data.get("max_results", 500))
    query_name = data.get("query_name", f"pce_events_{now.strftime('%H%M%S')}")

    query = {
        "query_name": query_name,
        "start_date": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_date": until.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policy_decisions": policy_decisions,
        "max_results": max_results,
        "sources": {"include": src_include or [], "exclude": src_exclude},
        "destinations": {"include": dst_include or [], "exclude": dst_exclude},
        "sources_destinations_query_op": data.get("query_op", "and"),
        "services": {"include": svc_include, "exclude": svc_exclude},
    }

    result = pce.create_traffic_query(query)
    if not result:
        return jsonify({"error": "Failed to create traffic query"}), 500

    return jsonify({"ok": True, "query": query, "result": result})


@bp.route("/api/traffic/queries")
@_auth_required
def api_traffic_queries() -> Any:
    """List all async traffic queries and their status."""
    pce = _get_pce_client()
    if not pce:
        return jsonify({"error": "PCE client not available"}), 503
    return jsonify(pce.list_traffic_queries())


@bp.route("/api/traffic/download")
@_auth_required
def api_traffic_download() -> Any:
    """Download traffic query results and return as parsed JSON rows."""
    import csv
    import io

    pce = _get_pce_client()
    if not pce:
        return jsonify({"error": "PCE client not available"}), 503

    href = request.args.get("href", "")
    if not href:
        return jsonify({"error": "href parameter required"}), 400

    csv_text = pce.download_traffic_results(href)
    if csv_text is None:
        return jsonify({"error": "Failed to download results"}), 500

    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    return jsonify({"flows": rows, "total": len(rows)})


@bp.route("/api/traffic/watchers", methods=["GET"])
@_auth_required
def api_traffic_watchers_list() -> Any:
    """List configured traffic watchers."""
    config = _get_config()
    return jsonify([tw.model_dump() for tw in config.traffic_watchers])


@bp.route("/api/traffic/watchers", methods=["POST"])
@_auth_required
def api_traffic_watcher_create() -> Any:
    """Create a traffic watcher from a flow or manual input."""
    config = _get_config()
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    name = data.get("name", "")
    if not name:
        return jsonify({"error": "name is required"}), 400

    tw = TrafficWatcher(
        name=name,
        src_include=data.get("src_include", ""),
        src_exclude=data.get("src_exclude", ""),
        dst_include=data.get("dst_include", ""),
        dst_exclude=data.get("dst_exclude", ""),
        services_include=data.get("services_include", ""),
        services_exclude=data.get("services_exclude", ""),
        policy_decisions=data.get("policy_decisions",
                                  ["blocked", "potentially_blocked"]),
        plugin=data.get("plugin", "PCEStdout"),
        template=data.get("template", "default.html"),
        interval=data.get("interval", "24h"),
        max_results=int(data.get("max_results", 500)),
    )

    config.traffic_watchers.append(tw)
    _persist_config()
    logger.info("Traffic watcher created: %s -> %s", name, tw.plugin)
    return jsonify({"ok": True, "name": name, "plugin": tw.plugin})


@bp.route("/api/traffic/watchers/<int:index>", methods=["DELETE"])
@_auth_required
def api_traffic_watcher_delete(index: int) -> Any:
    """Delete a traffic watcher by index."""
    config = _get_config()
    if 0 <= index < len(config.traffic_watchers):
        removed = config.traffic_watchers.pop(index)
        _persist_config()
        return jsonify({"ok": True, "removed": removed.name})
    return jsonify({"error": "Index out of range"}), 404


@bp.route("/api/render", methods=["POST"])
@_auth_required
def api_render_template() -> Any:
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    event_data = data.get("event")
    template_name = data.get("template", "default.html")
    if not event_data:
        return jsonify({"error": "event is required"}), 400

    config = _get_config()
    template_globals = {"pce_fqdn": config.pce.pce, "pce_org": config.pce.pce_org}

    template_dir = str(importlib.resources.files("pretty_cool_events") / "templates")
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["json_filter"] = lambda v: json.dumps(v, indent=4, sort_keys=True, ensure_ascii=True)

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
@_auth_required
def api_list_templates() -> Any:
    template_dir = importlib.resources.files("pretty_cool_events") / "templates"
    templates = []
    for item in template_dir.iterdir():
        name = item.name
        if name.startswith("_"):
            continue
        templates.append(name)
    return jsonify(sorted(templates))


@bp.route("/api/stream")
@_auth_required
def api_event_stream() -> Response:
    """Server-Sent Events endpoint for live event updates."""
    stats = _get_stats()
    q = stats.subscribe()

    def generate() -> Any:
        # Send initial stats snapshot
        snap = json.dumps({"type": "stats", **stats.snapshot()}, default=str)
        yield f"data: {snap}\n\n"

        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    # Send keepalive
                    yield ": keepalive\n\n"
        except GeneratorExit:
            stats.unsubscribe(q)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.route("/api/stats")
@_auth_required
def api_stats() -> Any:
    return jsonify(_get_stats().snapshot())


@bp.route("/api/health")
def api_health() -> Any:
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def _parse_time(value: str | None, now: datetime) -> datetime | None:
    if not value:
        return None
    match = re.match(r"^(\d+)([mhdw])$", value.strip())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        deltas = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount),
                  "d": timedelta(days=amount), "w": timedelta(weeks=amount)}
        return now - deltas[unit]
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _apply_filters(
    events: list[dict[str, Any]], event_type: str = "", status: str = "",
    severity: str = "", search: str = "", created_by: str = "", username: str = "",
) -> list[dict[str, Any]]:
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
        ul = username.lower()
        result = [e for e in result
                  if ul in ((e.get("created_by") or {}).get("user", {}).get("username", "")).lower()]
    if search:
        sl = search.lower()
        result = [e for e in result if _event_contains(e, sl)]
    return result


def _event_contains(event: dict[str, Any], search: str) -> bool:
    def _s(obj: Any) -> bool:
        if isinstance(obj, str):
            return search in obj.lower()
        if isinstance(obj, dict):
            return any(_s(v) for v in obj.values())
        if isinstance(obj, list):
            return any(_s(item) for item in obj)
        return False
    return _s(event)
