"""Web UI routes with authentication, config persistence, and SSE."""

from __future__ import annotations

import functools
import importlib.resources
import json
import logging
import queue
import re
import time
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
            labels = pce.get_labels(web=True)
            resolver.load(labels)
            logger.info("Loaded %d labels (%d keys)", len(labels), len(resolver.label_keys))
    return resolver


def _list_output_templates() -> list[str]:
    """List available output template filenames."""
    template_dir = importlib.resources.files("pretty_cool_events") / "templates"
    return sorted(f.name for f in template_dir.iterdir() if not f.name.startswith("_"))


def _validate_template_name(name: str) -> str | None:
    """Validate a template name is safe (no path traversal). Returns cleaned name or None."""
    if not name:
        return None
    # Strip path components - only allow bare filenames
    clean = name.replace("\\", "/").split("/")[-1]
    if ".." in clean or clean.startswith("_"):
        return None
    allowed = _list_output_templates()
    return clean if clean in allowed else None


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


_login_attempts: dict[str, list[float]] = {}  # IP -> list of attempt timestamps
_LOGIN_RATE_LIMIT = 5  # max attempts
_LOGIN_RATE_WINDOW = 300  # per 5 minutes


@bp.route("/login", methods=["GET", "POST"])
def login_page() -> Any:
    config = _get_config()
    if not (config.httpd.username and config.httpd.password):
        return redirect(url_for("main.index"))

    if request.method == "POST":
        # Rate limiting by IP
        client_ip = request.remote_addr or "unknown"
        now = time.monotonic()
        attempts = _login_attempts.setdefault(client_ip, [])
        attempts[:] = [t for t in attempts if t > now - _LOGIN_RATE_WINDOW]
        if len(attempts) >= _LOGIN_RATE_LIMIT:
            flash("Too many login attempts. Try again later.", "danger")
            return render_template("login.html"), 429

        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == config.httpd.username and password == config.httpd.password:
            session.clear()  # Prevent session fixation
            session["authenticated"] = True
            # Validate redirect target (prevent open redirect)
            next_url = request.args.get("next", "/")
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = "/"
            return redirect(next_url)

        attempts.append(now)
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
    stats = _get_stats().snapshot()
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
        enabled_plugins_json=json.dumps(list(config.plugin_config.keys())),
        stats_json=json.dumps(stats, default=str),
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
        for key in ["pce", "pce_api_user", "pce_org", "pce_poll_interval", "pce_timeout"]:
            val = request.form.get(key)
            if val is not None:
                if key in ("pce_org", "pce_poll_interval", "pce_timeout"):
                    try:
                        setattr(config.pce, key, int(val))
                    except ValueError:
                        flash(f"Invalid value for {key}: {val}", "danger")
                else:
                    setattr(config.pce, key, val)

        config.httpd.enabled = "httpd" in request.form

        # Throttle
        throttle_val = request.form.get("throttle_default", "")
        config.throttle_default = throttle_val
        throttler = current_app.config.get("THROTTLER")
        if throttler:
            throttler.update_default(throttle_val)

        # Auth settings
        new_user = request.form.get("httpd_username", "")
        new_pass = request.form.get("httpd_password", "")
        config.httpd.username = new_user
        if new_pass:  # Only update password if provided (don't blank it on empty form)
            config.httpd.password = new_pass

        # Warn if auth is only partially configured
        if bool(config.httpd.username) != bool(config.httpd.password):
            flash("Warning: set both username AND password to enable auth, or leave both empty", "warning")

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
            if not pattern or len(pattern) > 200:
                continue
            try:
                re.compile(pattern)
            except re.error:
                flash(f"Invalid regex pattern: {pattern}", "danger")
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

    output_templates = _list_output_templates()
    return render_template(
        "watchers.html", config=config, watchers=config.watchers,
        event_types=event_types, output_templates=output_templates,
    )


@bp.route("/watchers/delete", methods=["POST"])
@_auth_required
def delete_watcher() -> str:
    config = _get_config()
    pattern = request.form.get("pattern", "")
    index = request.form.get("index")

    if pattern in config.watchers and index is not None:
        try:
            idx = int(index)
        except ValueError:
            return redirect(url_for("main.watchers_page"))
        if 0 <= idx < len(config.watchers[pattern]):
            config.watchers[pattern].pop(idx)
            if not config.watchers[pattern]:
                del config.watchers[pattern]
            _persist_config()
            flash(f"Watcher removed: {pattern}", "success")

    return redirect(url_for("main.watchers_page"))


@bp.route("/api/watchers/update", methods=["PUT"])
@_auth_required
def api_update_watcher() -> Any:
    """Update an existing watcher action."""
    config = _get_config()
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    pattern = data.get("pattern", "")
    index = data.get("index")
    if pattern not in config.watchers or index is None:
        return jsonify({"error": "Watcher not found"}), 404

    try:
        idx = int(index)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid index"}), 400

    if not (0 <= idx < len(config.watchers[pattern])):
        return jsonify({"error": "Index out of range"}), 404

    action = config.watchers[pattern][idx]
    if "status" in data:
        action.status = data["status"]
    if "plugin" in data:
        action.plugin = data["plugin"]
    if "severity" in data:
        action.severity = data["severity"]
    if "template" in data:
        action.extra_data["template"] = data["template"]

    _persist_config()
    logger.info("Watcher updated: %s[%d] -> %s", pattern, idx, action.plugin)
    return jsonify({"ok": True, "pattern": pattern})


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
    try:
        max_results = min(int(request.args.get("max_results", "500")), 10000)
    except ValueError:
        max_results = 500

    now = datetime.now(timezone.utc)
    since = _parse_time(since_param, now)
    until = _parse_time(until_param, now) if until_param else now

    events = pce_client.get_events(since=since, until=until, max_results=max_results, web=True)

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
    if len(pattern) > 200:
        return jsonify({"error": "pattern too long"}), 400
    # Validate regex is compilable
    try:
        re.compile(pattern)
    except re.error:
        return jsonify({"error": "invalid regex pattern"}), 400

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
    try:
        max_results = min(int(data.get("max_results", 500)), 10000)
    except (ValueError, TypeError):
        max_results = 500
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

    result = pce.create_traffic_query(query, web=True)
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
    return jsonify(pce.list_traffic_queries(web=True))


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

    csv_text = pce.download_traffic_results(href, web=True)
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


@bp.route("/api/traffic/watchers/<int:index>", methods=["PUT"])
@_auth_required
def api_traffic_watcher_update(index: int) -> Any:
    """Update a traffic watcher by index."""
    config = _get_config()
    if not (0 <= index < len(config.traffic_watchers)):
        return jsonify({"error": "Index out of range"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    tw = config.traffic_watchers[index]
    for field in ("name", "src_include", "src_exclude", "dst_include", "dst_exclude",
                  "services_include", "services_exclude", "plugin", "template", "interval"):
        if field in data:
            setattr(tw, field, data[field])
    if "policy_decisions" in data:
        tw.policy_decisions = data["policy_decisions"]
    if "max_results" in data:
        import contextlib

        with contextlib.suppress(ValueError, TypeError):
            tw.max_results = min(int(data["max_results"]), 10000)

    _persist_config()
    logger.info("Traffic watcher updated: %s", tw.name)
    return jsonify({"ok": True, "name": tw.name})


@bp.route("/api/render", methods=["POST"])
@_auth_required
def api_render_template() -> Any:
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    event_data = data.get("event")
    raw_template = data.get("template", "default.html")
    if not event_data:
        return jsonify({"error": "event is required"}), 400

    template_name = _validate_template_name(raw_template)
    if not template_name:
        return jsonify({"error": f"Invalid template: {raw_template}"}), 400

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
    except Exception:
        logger.exception("Template render failed: %s", template_name)
        return jsonify({"error": "Template render failed", "template": template_name}), 400


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


@bp.route("/api/throttle")
@_auth_required
def api_throttle() -> Any:
    """Return throttle state and suppressed event counts."""
    throttler = current_app.config.get("THROTTLER")
    if not throttler:
        return jsonify({"default": "", "active_keys": 0, "total_suppressed": 0, "suppressed_by_key": {}})
    return jsonify(throttler.snapshot())


@bp.route("/api/stats")
@_auth_required
def api_stats() -> Any:
    return jsonify(_get_stats().snapshot())


@bp.route("/api/health")
def api_health() -> Any:
    return jsonify({"status": "ok"})


# --- Plugin verification ---

_plugin_verify_codes: dict[str, dict[str, Any]] = {}  # plugin_name -> {code, timestamp, verified}


@bp.route("/api/plugins/verify", methods=["POST"])
@_auth_required
def api_plugin_verify() -> Any:
    """Send a verification code through a plugin to test configuration."""
    import secrets
    import string

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    plugin_name = data.get("plugin", "")
    if not plugin_name:
        return jsonify({"error": "plugin name required"}), 400

    config = _get_config()
    if plugin_name not in config.plugin_config:
        return jsonify({"error": f"Plugin '{plugin_name}' not configured"}), 400

    # Generate a 6-char verification code
    code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))

    # Build a verification event
    verify_event = {
        "event_type": "plugin.verification",
        "status": "success",
        "severity": "info",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pce_fqdn": config.pce.pce,
        "href": "/verification",
        "created_by": {"system": {}},
        "verification_code": code,
        "notifications": [],
        "resource_changes": [],
        "action": None,
    }

    template_globals = {"pce_fqdn": config.pce.pce, "pce_org": config.pce.pce_org}

    # Get the extra_data from the request (channel, email_to, etc.)
    extra_data = data.get("extra_data", {})
    extra_data.setdefault("template", "verify.html")

    # Load and send through the plugin
    from pretty_cool_events.plugins.base import get_registry, load_all_plugins

    load_all_plugins()
    registry = get_registry()

    if plugin_name not in registry:
        return jsonify({"error": f"Plugin class '{plugin_name}' not found"}), 400

    plugin = registry[plugin_name]()
    plugin.configure(config.get_plugin_config(plugin_name))

    try:
        plugin.send(verify_event, extra_data, template_globals)
        _plugin_verify_codes[plugin_name] = {
            "code": code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "verified": False,
        }
        return jsonify({"ok": True, "code": code, "plugin": plugin_name})
    except Exception as e:
        logger.exception("Plugin verification send failed: %s", plugin_name)
        return jsonify({"error": f"Send failed: {e}"}), 500


@bp.route("/api/plugins/verify/confirm", methods=["POST"])
@_auth_required
def api_plugin_verify_confirm() -> Any:
    """Confirm a verification code was received at the destination."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    plugin_name = data.get("plugin", "")
    code = data.get("code", "").strip().upper()

    pending = _plugin_verify_codes.get(plugin_name)
    if not pending:
        return jsonify({"error": "No pending verification for this plugin"}), 400

    if pending["code"] == code:
        pending["verified"] = True
        return jsonify({"ok": True, "verified": True, "plugin": plugin_name})
    return jsonify({"ok": False, "verified": False, "error": "Code does not match"}), 400


@bp.route("/api/plugins/verify/status")
@_auth_required
def api_plugin_verify_status() -> Any:
    """Get verification status for all plugins."""
    return jsonify(_plugin_verify_codes)


# --- Watcher dry-run ---

@bp.route("/api/watchers/test", methods=["POST"])
@_auth_required
def api_watcher_test() -> Any:
    """Test a watcher pattern against recent events (dry-run)."""
    pce = _get_pce_client()
    if not pce:
        return jsonify({"error": "PCE not available"}), 503

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body"}), 400

    pattern = data.get("pattern", "")
    status_filter = data.get("status", "*")
    match_fields = data.get("match_fields", {})
    max_events = min(int(data.get("max_events", 100)), 500)

    from pretty_cool_events.config import WatcherAction
    from pretty_cool_events.watcher import WatcherRegistry

    action = WatcherAction(
        status=status_filter,
        plugin="PCEStdout",
        extra_data={"match_fields": match_fields} if match_fields else {},
    )
    registry = WatcherRegistry({pattern: [action]})

    # Fetch recent events
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    events = pce.get_events(since=since, until=now, max_results=max_events, web=True)

    matches = []
    for evt in events:
        results = registry.match(evt)
        if results:
            matches.append({
                "event_type": evt.get("event_type"),
                "status": evt.get("status"),
                "severity": evt.get("severity"),
                "timestamp": evt.get("timestamp"),
                "created_by": evt.get("created_by"),
            })

    return jsonify({
        "pattern": pattern,
        "status": status_filter,
        "events_checked": len(events),
        "matches": matches,
        "match_count": len(matches),
    })


# --- Config export/import ---

@bp.route("/api/config/export")
@_auth_required
def api_config_export() -> Any:
    """Download the current config as YAML."""
    config = _get_config()

    import io

    buf = io.StringIO()
    # Build the YAML manually using save_config's logic
    import yaml as _yaml

    flat: dict[str, Any] = {
        "pce": config.pce.pce,
        "pce_api_user": config.pce.pce_api_user,
        "pce_api_secret": config.pce.pce_api_secret,
        "pce_org": config.pce.pce_org,
        "pce_poll_interval": config.pce.pce_poll_interval,
        "httpd": config.httpd.enabled,
        "httpd_listener_address": config.httpd.address,
        "httpd_listener_port": config.httpd.port,
        "httpd_username": config.httpd.username,
        "httpd_password": config.httpd.password,
        "default_template": config.default_template,
        "throttle_default": config.throttle_default,
        "plugin_config": config.plugin_config,
    }
    watchers_out = {p: [a.model_dump() for a in actions]
                    for p, actions in config.watchers.items()}
    output: dict[str, Any] = {"config": flat, "watchers": watchers_out}
    if config.traffic_watchers:
        output["traffic_watchers"] = [tw.model_dump() for tw in config.traffic_watchers]

    _yaml.dump(output, buf, default_flow_style=False, sort_keys=False)

    return Response(
        buf.getvalue(),
        mimetype="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=config.yaml"},
    )


@bp.route("/api/config/import", methods=["POST"])
@_auth_required
def api_config_import() -> Any:
    """Upload a YAML config file to replace the current config."""
    import yaml as _yaml

    file = request.files.get("config_file")
    if not file:
        flash("No file uploaded", "danger")
        return redirect(url_for("main.config_page"))

    try:
        raw = _yaml.safe_load(file.read())
        if not raw or "config" not in raw:
            flash("Invalid config file format", "danger")
            return redirect(url_for("main.config_page"))

        from pretty_cool_events.config import _apply_env_overrides, _normalize_raw_config

        raw = _apply_env_overrides(raw)
        normalized = _normalize_raw_config(raw)

        config = _get_config()
        # Update in-memory config
        from pretty_cool_events.config import AppConfig

        new_config = AppConfig(**normalized)
        new_config.config_path = config.config_path

        # Replace the app's config
        current_app.config["APP_CONFIG"] = new_config
        _persist_config()
        flash("Configuration imported successfully", "success")
    except Exception:
        logger.exception("Config import failed")
        flash("Import failed: check file format", "danger")

    return redirect(url_for("main.config_page"))


# --- Notification history ---

@bp.route("/api/history")
@_auth_required
def api_dispatch_history() -> Any:
    """Return the dispatch notification history."""
    stats = _get_stats()
    snap = stats.snapshot()
    return jsonify(snap.get("dispatch_history", []))


# --- Suppression window ---

@bp.route("/api/suppression", methods=["GET", "POST", "DELETE"])
@_auth_required
def api_suppression() -> Any:
    """Manage the notification suppression window."""
    throttler = current_app.config.get("THROTTLER")

    if request.method == "POST":
        data = request.get_json() or {}
        minutes = int(data.get("minutes", 60))
        reason = data.get("reason", "maintenance")
        if throttler:
            throttler.set_suppression(minutes, reason)
        return jsonify({"ok": True, "minutes": minutes, "reason": reason})

    if request.method == "DELETE":
        if throttler:
            throttler.clear_suppression()
        return jsonify({"ok": True, "cleared": True})

    # GET
    if throttler:
        return jsonify({
            "active": throttler.is_suppressed(),
            "remaining_min": throttler.suppression_remaining(),
            "reason": throttler._suppression_reason,
        })
    return jsonify({"active": False, "remaining_min": 0, "reason": ""})


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
