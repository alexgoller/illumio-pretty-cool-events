"""CLI interface using Click."""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
from typing import Any

import click
import yaml
from rich.console import Console
from rich.table import Table

from pretty_cool_events.config import (
    WatcherAction,
    load_config,
    load_event_types,
    save_config,
)

console = Console()


def _setup_logging(level: str) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(stream=sys.stdout, level=getattr(logging, level.upper()), format=fmt)


@click.group()
@click.version_option(package_name="pretty-cool-events")
def cli() -> None:
    """Illumio PCE event monitoring and notification system."""


_DEFAULT_CONFIG_PATH = "/config/config.yaml"


@cli.command()
@click.option("--config", "config_path", required=False, type=click.Path(),
              help="Path to config YAML file (auto-creates bootstrap config if not found)")
@click.option("--log-level", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False))
def run(config_path: str | None, log_level: str) -> None:
    """Run the event monitoring service.

    If --config is not provided, looks for config at /config/config.yaml
    (Docker default) then ./config.yaml. If no config exists, creates a
    bootstrap config with the web UI enabled for browser-based setup.
    """
    _setup_logging(log_level)
    logger = logging.getLogger(__name__)

    from pretty_cool_events.config import create_bootstrap_config

    # Resolve config path with fallback chain
    if config_path is None:
        from pathlib import Path
        candidates = [Path(_DEFAULT_CONFIG_PATH), Path("config.yaml")]
        config_path = next((str(p) for p in candidates if p.is_file()), None)

    if config_path and os.path.isfile(config_path):
        try:
            app_config = load_config(config_path)
            console.print(f"[green]Loaded config:[/green] {config_path}")
        except Exception as e:
            console.print(f"[red]Config error:[/red] {e}")
            raise SystemExit(1) from e
    else:
        # Bootstrap mode: generate minimal config
        bootstrap_path = config_path or "config.yaml"
        console.print(f"[yellow]No config found. Creating bootstrap config: {bootstrap_path}[/yellow]")
        console.print("[yellow]Web UI enabled - configure via browser.[/yellow]")
        app_config = create_bootstrap_config(bootstrap_path)

    from pretty_cool_events.event_loop import EventLoop, TrafficWatcherLoop
    from pretty_cool_events.pce_client import PCEClient
    from pretty_cool_events.plugins.base import create_plugins
    from pretty_cool_events.stats import StatsTracker
    from pretty_cool_events.watcher import WatcherRegistry

    stats = StatsTracker()
    plugins: dict[str, Any] = {}
    pce_client: PCEClient | None = None
    loops_to_stop: list[Any] = []

    # Only start PCE polling if credentials are configured
    has_pce = bool(app_config.pce.pce and app_config.pce.pce_api_user and app_config.pce.pce_api_secret)

    if has_pce:
        pce_client = PCEClient(
            base_url=app_config.pce.pce,
            api_user=app_config.pce.pce_api_user,
            api_secret=app_config.pce.pce_api_secret,
            org_id=app_config.pce.pce_org,
            verify_tls=app_config.pce.verify_tls,
        )

        if not pce_client.health_check():
            console.print("[yellow]Warning:[/yellow] PCE health check failed. Continuing anyway...")

        plugins = create_plugins(app_config)
        watcher_registry = WatcherRegistry(app_config.watchers)
        event_loop = EventLoop(pce_client, watcher_registry, stats, plugins, app_config)
        loops_to_stop.append(event_loop)

        event_thread = threading.Thread(target=event_loop.run, name="event-loop", daemon=True)
        event_thread.start()
        logger.info("Event loop started")

        if app_config.traffic_watchers:
            traffic_loop = TrafficWatcherLoop(pce_client, app_config, stats, plugins)
            loops_to_stop.append(traffic_loop)
            traffic_thread = threading.Thread(
                target=traffic_loop.run, name="traffic-watchers", daemon=True
            )
            traffic_thread.start()
            logger.info("Traffic watcher loop started (%d watchers)", len(app_config.traffic_watchers))
    else:
        console.print("[yellow]PCE not configured. Web UI only (configure via browser).[/yellow]")

    # Start web UI if configured (always starts in bootstrap mode)
    if app_config.httpd.enabled or not has_pce:
        from pretty_cool_events.web.app import create_app

        throttler = loops_to_stop[0].throttler if loops_to_stop and hasattr(loops_to_stop[0], 'throttler') else None
        flask_app = create_app(app_config, stats, plugins, pce_client=pce_client,
                               throttler=throttler)
        web_thread = threading.Thread(
            target=lambda: flask_app.run(
                host=app_config.httpd.address,
                port=app_config.httpd.port,
                use_reloader=False,
            ),
            name="web-ui",
            daemon=True,
        )
        web_thread.start()
        logger.info("Web UI started on %s:%d", app_config.httpd.address, app_config.httpd.port)

    # Graceful shutdown
    shutdown_event = threading.Event()

    def _shutdown(signum: int, frame: Any) -> None:
        console.print("\n[yellow]Shutting down...[/yellow]")
        for loop in loops_to_stop:
            loop.stop()
        shutdown_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if has_pce:
        console.print("[green]Service running.[/green] Press Ctrl+C to stop.")
    else:
        console.print(f"[green]Web UI running on http://0.0.0.0:{app_config.httpd.port}[/green]")
        console.print("[yellow]Configure PCE credentials in the browser to start monitoring.[/yellow]")

    # Block until shutdown
    if has_pce:
        event_thread.join()
        pce_client.close()
    else:
        shutdown_event.wait()

    console.print("[green]Shutdown complete.[/green]")


@cli.group()
def config() -> None:
    """Configuration management commands."""


@config.command("validate")
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
def config_validate(config_path: str) -> None:
    """Validate a configuration file."""
    try:
        app_config = load_config(config_path)
        console.print("[green]Configuration is valid.[/green]")
        console.print(f"  PCE: {app_config.pce.pce}")
        console.print(f"  Org: {app_config.pce.pce_org}")
        console.print(f"  Poll interval: {app_config.pce.pce_poll_interval}s")
        console.print(f"  Watchers: {len(app_config.watchers)}")
        console.print(f"  Active plugins: {', '.join(app_config.get_active_plugins())}")
    except Exception as e:
        console.print(f"[red]Validation failed:[/red] {e}")
        raise SystemExit(1) from e


@config.command("show")
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
def config_show(config_path: str) -> None:
    """Display configuration with secrets masked."""
    try:
        app_config = load_config(config_path)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from e

    data = app_config.model_dump()
    _mask_secrets(data)
    console.print_json(json.dumps(data, indent=2, default=str))


def _mask_secrets(data: Any, _secret_keys: set[str] | None = None) -> None:
    if _secret_keys is None:
        _secret_keys = {"pce_api_secret", "smtp_password", "api_token", "api_key",
                        "slack_bot_token", "client_secret", "signing_secret",
                        "bearer_token", "password", "access_key_secret",
                        "access_key", "pd_from"}
    if isinstance(data, dict):
        for key in data:
            if key in _secret_keys and isinstance(data[key], str) and data[key]:
                data[key] = "********"
            else:
                _mask_secrets(data[key], _secret_keys)
    elif isinstance(data, list):
        for item in data:
            _mask_secrets(item, _secret_keys)


@config.command("init")
@click.option("--output", "output_path", default="config.yaml",
              help="Output file path")
def config_init(output_path: str) -> None:
    """Interactively create a new configuration file."""
    console.print("[bold]Pretty Cool Events - Configuration Wizard[/bold]\n")

    pce = click.prompt("PCE hostname (e.g., pce.example.com)")
    api_user = click.prompt("API user (e.g., api_xxx)")
    api_secret = click.prompt("API secret", hide_input=True)
    org = click.prompt("Organization ID", type=int, default=1)
    poll_interval = click.prompt("Poll interval (seconds)", type=int, default=10)
    enable_httpd = click.confirm("Enable web UI?", default=True)

    config_data: dict[str, Any] = {
        "config": {
            "pce": pce,
            "pce_api_user": api_user,
            "pce_api_secret": api_secret,
            "pce_org": org,
            "pce_poll_interval": poll_interval,
            "httpd": enable_httpd,
            "httpd_listener_port": 8443,
            "default_template": "default.html",
            "plugin_config": {
                "PCEStdout": {"prepend": ""},
            },
        },
        "watchers": {
            ".*": [
                {
                    "status": "success",
                    "plugin": "PCEStdout",
                    "extra_data": {"template": "default.html"},
                }
            ],
        },
    }

    with open(output_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

    console.print(f"\n[green]Configuration written to {output_path}[/green]")
    console.print("A catch-all watcher (.*) with PCEStdout has been added as a starting point.")
    console.print(f"Edit {output_path} to add more watchers and plugin configurations.")


@cli.group()
def watcher() -> None:
    """Watcher management commands."""


@watcher.command("list")
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
def watcher_list(config_path: str) -> None:
    """List all configured watchers."""
    try:
        app_config = load_config(config_path)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from e

    table = Table(title="Configured Watchers")
    table.add_column("Pattern", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Plugin", style="magenta")
    table.add_column("Severity")
    table.add_column("Template")

    for pattern, actions in app_config.watchers.items():
        for action in actions:
            template = action.extra_data.get("template", app_config.default_template)
            table.add_row(pattern, action.status, action.plugin, action.severity, template)

    console.print(table)


@watcher.command("add")
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
def watcher_add(config_path: str) -> None:
    """Interactively add a new watcher."""
    try:
        app_config = load_config(config_path)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from e

    event_types = load_event_types()
    console.print(f"[dim]{len(event_types)} event types available. Use regex patterns like 'user.*'[/dim]\n")

    pattern = click.prompt("Event pattern (e.g., user.login, agent.*)")
    status = click.prompt("Status to match", type=click.Choice(["success", "failure"]),
                          default="success")
    plugin = click.prompt("Plugin name", type=click.Choice(
        ["PCEStdout", "PCESlack", "PCEMail", "PCESNS", "PCESyslog",
         "PCEWebhook", "PCEJira", "PCETeams", "PCEServiceNow",
         "PCEPagerDuty", "PCEFile"]))
    template = click.prompt("Template", default="default.html")

    action = WatcherAction(
        status=status,
        plugin=plugin,
        extra_data={"template": template},
    )

    if pattern in app_config.watchers:
        app_config.watchers[pattern].append(action)
    else:
        app_config.watchers[pattern] = [action]

    save_config(app_config, config_path)
    console.print(f"[green]Watcher added:[/green] {pattern} -> {plugin}")


@cli.command("test-plugin")
@click.argument("plugin_name")
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
def test_plugin(plugin_name: str, config_path: str) -> None:
    """Send a test event through a plugin to verify configuration."""
    _setup_logging("DEBUG")

    try:
        app_config = load_config(config_path)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from e


    # Temporarily add the plugin to active set
    if plugin_name not in app_config.plugin_config:
        console.print(f"[red]Plugin '{plugin_name}' not found in config[/red]")
        raise SystemExit(1)

    from pretty_cool_events.plugins.base import get_registry, load_all_plugins

    load_all_plugins()
    registry = get_registry()

    if plugin_name not in registry:
        console.print(f"[red]Plugin '{plugin_name}' not registered[/red]")
        raise SystemExit(1)

    plugin = registry[plugin_name]()
    plugin.configure(app_config.get_plugin_config(plugin_name))

    test_event = {
        "event_type": "test.pretty_cool_events",
        "status": "success",
        "severity": "info",
        "timestamp": "2024-01-01T00:00:00Z",
        "href": "/orgs/1/events/test",
        "created_by": {"user": {"username": "test-user"}},
    }

    template_globals = {
        "pce_fqdn": app_config.pce.pce,
        "pce_org": app_config.pce.pce_org,
    }

    console.print(f"Sending test event to [cyan]{plugin_name}[/cyan]...")
    try:
        plugin.send(test_event, {"template": "default.html"}, template_globals)
        console.print("[green]Test event sent successfully![/green]")
    except Exception as e:
        console.print(f"[red]Plugin error:[/red] {e}")
        raise SystemExit(1) from e
