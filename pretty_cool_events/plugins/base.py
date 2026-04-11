"""Base plugin class with auto-registration and template rendering."""

from __future__ import annotations

import importlib.resources
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

# Global plugin registry populated by __init_subclass__
_PLUGIN_REGISTRY: dict[str, type[OutputPlugin]] = {}


def _get_template_dir() -> str:
    """Resolve the output templates directory from the package."""
    ref = importlib.resources.files("pretty_cool_events") / "templates"
    # Use as_file for traversable resources
    return str(ref)


def _json_filter(value: Any) -> str:
    return json.dumps(value, indent=4, sort_keys=True, ensure_ascii=True)


class OutputPlugin(ABC):
    """Abstract base class for all output plugins."""

    name: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.name:
            _PLUGIN_REGISTRY[cls.name] = cls
            logger.debug("Registered plugin: %s", cls.name)

    def __init__(self) -> None:
        template_dir = _get_template_dir()
        self._env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=ChainableUndefined,
        )
        self._env.filters["json_filter"] = _json_filter
        self._configured = False

    def render_template(self, template_name: str, event: dict[str, Any],
                        template_globals: dict[str, Any] | None = None) -> str:
        """Render an output template with event data and globals.

        Templates get access to:
        - All event fields as top-level variables (e.g., {{ event_type }})
        - The full event dict as {{ event }} (for templates using event.field syntax)
        - All template_globals as top-level variables (e.g., {{ pce_fqdn }})
        Event fields take precedence over template_globals on collision.
        """
        # Security: strip path components to prevent directory traversal
        safe_name = template_name.replace("\\", "/").split("/")[-1]
        if ".." in safe_name:
            raise ValueError(f"Invalid template name: {template_name}")

        context: dict[str, Any] = {}
        if template_globals:
            context.update(template_globals)
        context.update(event)  # Event fields override globals
        context["event"] = event  # Also available as nested object
        template = self._env.get_template(safe_name)
        rendered = template.render(**context)

        # Warn if template rendered empty (likely wrong template for event type)
        stripped = rendered.strip()
        if not stripped:
            logger.warning(
                "Template '%s' rendered EMPTY for event '%s' - "
                "wrong template for this event type? "
                "Traffic events need traffic-* templates, PCE events need standard templates.",
                safe_name, event.get("event_type", "?"),
            )
        return rendered

    @abstractmethod
    def configure(self, config: dict[str, Any]) -> None:
        """Configure the plugin with settings from the config file."""

    @abstractmethod
    def send(self, event: dict[str, Any], extra_data: dict[str, Any],
             template_globals: dict[str, Any]) -> None:
        """Process and send an event notification."""


def get_registry() -> dict[str, type[OutputPlugin]]:
    """Return the plugin registry."""
    return dict(_PLUGIN_REGISTRY)


def load_all_plugins() -> None:
    """Auto-discover and import all plugin modules to trigger registration."""
    import importlib
    import pkgutil

    import pretty_cool_events.plugins as plugins_pkg

    for _importer, modname, _ispkg in pkgutil.iter_modules(plugins_pkg.__path__):
        if modname.startswith("_") or modname == "base":
            continue
        try:
            importlib.import_module(f"pretty_cool_events.plugins.{modname}")
        except Exception:
            logger.exception("Failed to load plugin module: %s", modname)


def create_plugins(config: Any) -> dict[str, OutputPlugin]:
    """Discover, instantiate, and configure all active plugins."""
    load_all_plugins()
    registry = get_registry()
    active_names = config.get_active_plugins()
    plugins: dict[str, OutputPlugin] = {}

    for name in active_names:
        if name not in registry:
            logger.warning("Plugin '%s' referenced in watchers but not found", name)
            continue
        plugin = registry[name]()
        plugin_config = config.get_plugin_config(name)
        plugin.configure(plugin_config)
        plugins[name] = plugin
        logger.info("Activated plugin: %s", name)

    return plugins
