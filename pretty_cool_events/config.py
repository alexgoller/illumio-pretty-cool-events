"""Configuration loading, validation, and persistence using Pydantic v2."""

from __future__ import annotations

import importlib.resources
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class PCEConfig(BaseModel):
    """PCE connection settings."""

    pce: str
    pce_api_user: str
    pce_api_secret: str
    pce_org: int = 1
    pce_poll_interval: int = 10
    verify_tls: bool = True


class HttpdConfig(BaseModel):
    """Web UI settings."""

    enabled: bool = False
    address: str = "0.0.0.0"
    port: int = 8443
    username: str = ""
    password: str = ""


class StdoutPluginConfig(BaseModel):
    prepend: str = ""
    append: str = ""


class SlackPluginConfig(BaseModel):
    slack_bot_token: str = ""
    template: str = "default-slack.html"
    app_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    signing_secret: str = ""


class EmailPluginConfig(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""
    template: str = "email.tmpl"


class SNSPluginConfig(BaseModel):
    access_key: str = ""
    access_key_secret: str = ""
    aws_region_name: str = "us-east-1"


class SyslogPluginConfig(BaseModel):
    syslog_host: str = "localhost"
    syslog_port: int = 514
    syslog_cert_file: str = ""
    template: str = "syslog.tmpl"


class WebhookPluginConfig(BaseModel):
    url: str = ""
    bearer_token: str = ""
    data: str = ""


class JiraPluginConfig(BaseModel):
    jira_server: str = ""
    username: str = ""
    api_token: str = ""
    project: str = ""
    template: str = "default.html"


class TeamsPluginConfig(BaseModel):
    webhook: str = ""
    template: str = "default-teams.tmpl"


class ServiceNowPluginConfig(BaseModel):
    instance: str = ""
    username: str = ""
    password: str = ""
    template: str = "default.html"


class PagerDutyPluginConfig(BaseModel):
    api_key: str = ""
    pd_from: str = ""
    pd_priority: str = ""
    pd_service: str = ""
    template: str = "sms.tmpl"


class FilePluginConfig(BaseModel):
    logfile: str = "events.log"
    template: str = "default-json.html"


PLUGIN_CONFIG_MAP: dict[str, type[BaseModel]] = {
    "PCEStdout": StdoutPluginConfig,
    "PCESlack": SlackPluginConfig,
    "PCEMail": EmailPluginConfig,
    "PCESNS": SNSPluginConfig,
    "PCESyslog": SyslogPluginConfig,
    "PCEWebhook": WebhookPluginConfig,
    "PCEJira": JiraPluginConfig,
    "PCETeams": TeamsPluginConfig,
    "PCEServiceNow": ServiceNowPluginConfig,
    "PCEPagerDuty": PagerDutyPluginConfig,
    "PCEFile": FilePluginConfig,
}


class WatcherAction(BaseModel):
    """A single action to take when a watcher matches."""

    status: str = "success"
    severity: str = "info"
    plugin: str
    extra_data: dict[str, Any] = Field(default_factory=dict)


class TrafficWatcher(BaseModel):
    """A saved traffic flow query with notification routing."""

    name: str
    src_include: str = ""
    src_exclude: str = ""
    dst_include: str = ""
    dst_exclude: str = ""
    services_include: str = ""
    services_exclude: str = ""
    policy_decisions: list[str] = Field(
        default_factory=lambda: ["blocked", "potentially_blocked"]
    )
    plugin: str = "PCEStdout"
    template: str = "default.html"
    interval: str = "24h"
    max_results: int = 500


class AppConfig(BaseModel):
    """Top-level application configuration."""

    pce: PCEConfig
    httpd: HttpdConfig = Field(default_factory=HttpdConfig)
    default_template: str = "default.html"
    throttle_default: str = ""
    plugin_config: dict[str, dict[str, Any]] = Field(default_factory=dict)
    watchers: dict[str, list[WatcherAction]] = Field(default_factory=dict)
    traffic_watchers: list[TrafficWatcher] = Field(default_factory=list)
    config_path: str | None = Field(default=None, exclude=True)

    @field_validator("watchers", mode="before")
    @classmethod
    def validate_watchers(cls, v: Any) -> dict[str, list[WatcherAction]]:
        if v is None:
            return {}
        return v

    def get_plugin_config(self, plugin_name: str) -> dict[str, Any]:
        """Get validated config for a plugin."""
        raw = self.plugin_config.get(plugin_name, {})
        if raw is None:
            raw = {}
        model_cls = PLUGIN_CONFIG_MAP.get(plugin_name)
        if model_cls:
            return model_cls(**raw).model_dump()
        return raw

    def get_active_plugins(self) -> set[str]:
        """Return the set of plugin names referenced by watchers."""
        plugins: set[str] = set()
        for actions in self.watchers.values():
            for action in actions:
                plugins.add(action.plugin)
        return plugins


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides. Pattern: PCE_EVENTS_<SECTION>_<KEY>."""
    prefix = "PCE_EVENTS_"
    pce_section = raw.get("config", raw)

    env_map = {
        f"{prefix}PCE": ("pce",),
        f"{prefix}PCE_API_USER": ("pce_api_user",),
        f"{prefix}PCE_API_SECRET": ("pce_api_secret",),
        f"{prefix}PCE_ORG": ("pce_org",),
        f"{prefix}PCE_POLL_INTERVAL": ("pce_poll_interval",),
    }

    for env_key, path in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            target = pce_section
            for key in path[:-1]:
                target = target.setdefault(key, {})
            target[path[-1]] = val

    return raw


def _normalize_raw_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert the flat YAML structure into the nested Pydantic model structure."""
    config_section = raw.get("config", raw)
    watchers_section = raw.get("watchers", {})

    pce_keys = ["pce", "pce_api_user", "pce_api_secret", "pce_org",
                "pce_poll_interval", "verify_tls"]

    pce_config = {}
    for key in pce_keys:
        if key in config_section:
            pce_config[key] = config_section[key]

    httpd_config = {
        "enabled": config_section.get("httpd", False),
        "address": config_section.get("httpd_listener_address", "0.0.0.0"),
        "port": config_section.get("httpd_listener_port", 8443),
        "username": config_section.get("httpd_username", ""),
        "password": config_section.get("httpd_password", ""),
    }

    # Normalize None plugin configs to empty dicts
    raw_plugin_config = config_section.get("plugin_config", {}) or {}
    plugin_config = {k: (v if v is not None else {}) for k, v in raw_plugin_config.items()}

    traffic_watchers_section = raw.get("traffic_watchers", [])

    return {
        "pce": pce_config,
        "httpd": httpd_config,
        "default_template": config_section.get("default_template", "default.html"),
        "throttle_default": config_section.get("throttle_default", ""),
        "plugin_config": plugin_config,
        "watchers": watchers_section,
        "traffic_watchers": traffic_watchers_section or [],
    }


def create_bootstrap_config(path: Path | str) -> AppConfig:
    """Generate a minimal bootstrap config for first-run.

    Creates a config with web UI enabled, PCEStdout plugin, and a catch-all
    watcher. PCE credentials are blank - user configures via the web UI.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    raw: dict[str, Any] = {
        "config": {
            "pce": "",
            "pce_api_user": "",
            "pce_api_secret": "",
            "pce_org": 1,
            "pce_poll_interval": 10,
            "httpd": True,
            "httpd_listener_address": "0.0.0.0",
            "httpd_listener_port": 8443,
            "httpd_username": "",
            "httpd_password": "",
            "default_template": "default.html",
            "throttle_default": "",
            "plugin_config": {
                "PCEStdout": {"prepend": ""},
            },
        },
        "watchers": {
            ".*": [
                {
                    "status": "*",
                    "plugin": "PCEStdout",
                    "extra_data": {"template": "default.html"},
                }
            ],
        },
    }

    # Apply environment variable overrides (PCE_EVENTS_PCE, etc.)
    raw = _apply_env_overrides(raw)

    with open(path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, sort_keys=False)

    logger.info("Bootstrap config created: %s", path)
    normalized = _normalize_raw_config(raw)
    app_config = AppConfig(**normalized)
    app_config.config_path = str(path.resolve())
    return app_config


def load_config(path: Path | str) -> AppConfig:
    """Load and validate configuration from a YAML file."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError("Config file is empty")

    raw = _apply_env_overrides(raw)
    normalized = _normalize_raw_config(raw)
    app_config = AppConfig(**normalized)
    app_config.config_path = str(path.resolve())
    return app_config


def save_config(config: AppConfig, path: Path | str, backup: bool = True) -> None:
    """Save configuration to a YAML file, optionally creating a backup."""
    path = Path(path)

    if backup and path.exists():
        backup_dir = path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"config_backup_{timestamp}.yaml"
        shutil.copy2(path, backup_path)
        logger.info("Created config backup: %s", backup_path)

    # Convert back to the flat YAML format for backward compatibility
    flat_config: dict[str, Any] = {
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

    watchers_out: dict[str, list[dict[str, Any]]] = {}
    for pattern, actions in config.watchers.items():
        watchers_out[pattern] = [a.model_dump() for a in actions]

    traffic_watchers_out = [tw.model_dump() for tw in config.traffic_watchers]

    output: dict[str, Any] = {"config": flat_config, "watchers": watchers_out}
    if traffic_watchers_out:
        output["traffic_watchers"] = traffic_watchers_out

    with open(path, "w") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False)


def load_event_types() -> list[str]:
    """Load the catalog of known PCE event types."""
    data_path = importlib.resources.files("pretty_cool_events") / "data" / "event_types.yaml"
    with importlib.resources.as_file(data_path) as p, open(p) as f:
        data = yaml.safe_load(f)
    return data.get("event_types", [])
