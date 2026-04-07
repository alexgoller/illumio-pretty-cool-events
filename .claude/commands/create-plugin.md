# Create Plugin

Create a new Pretty Cool Events output plugin for $ARGUMENTS.

## Instructions

1. Run `pce-events create-plugin $ARGUMENTS` to scaffold the plugin boilerplate
2. Read the generated plugin file in `pretty_cool_events/plugins/`
3. Implement the `send()` method based on the service's API:
   - For HTTP-based services: use `httpx.post()` 
   - For SDK-based services: import and use the SDK
   - Always render the template first: `rendered = self.render_template(template_name, event, template_globals)`
   - Handle errors with try/except and log failures
4. Add config fields to `configure()` reading from the config dict
5. Add the plugin metadata to `pretty_cool_events/plugin_meta.py` in the `PLUGIN_METADATA` dict with:
   - `display_name`: human-readable name for the UI
   - `icon`: Bootstrap icon class (e.g., `bi-discord`, `bi-send`, `bi-chat`)
   - `description`: what the plugin does
   - `how_it_works`: setup instructions for the user
   - `fields`: dict of FieldMeta for each config field (label, help, required, secret, placeholder)
6. Write a test in `tests/test_plugins/` that mocks the external service and verifies the send method
7. Run `pytest tests/ -q` to verify
8. Run `ruff check pretty_cool_events/` to verify lint

The plugin will be auto-discovered at startup - no imports to add.

## Plugin Architecture

- Plugins inherit from `OutputPlugin` (ABC in `pretty_cool_events/plugins/base.py`)
- `name` class variable = the config key (e.g., `"PCEDiscord"`)
- `configure(config)` receives the dict from `plugin_config.PCEDiscord` in config.yaml
- `send(event, extra_data, template_globals)` is called for each matched event
- `self.render_template(name, event, globals)` renders a Jinja2 template
- Registration is automatic via `__init_subclass__`

## Example: Discord webhook plugin

```python
class DiscordPlugin(OutputPlugin):
    name = "PCEDiscord"

    def configure(self, config):
        self.webhook_url = config.get("webhook_url", "")

    def send(self, event, extra_data, template_globals):
        template_name = extra_data.get("template", "default.html")
        rendered = self.render_template(template_name, event, template_globals)
        import httpx
        httpx.post(self.webhook_url, json={"content": rendered})
```
