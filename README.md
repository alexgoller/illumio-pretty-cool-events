# Pretty Cool Events

Real-time event monitoring and notification system for the Illumio Policy Compute Engine (PCE). Continuously polls the PCE Events API, matches events against configurable watcher rules, and routes notifications to Slack, Email, PagerDuty, Jira, Teams, ServiceNow, and more.

## How It Works

```
Illumio PCE  -->  Event Polling  -->  Watcher Matching  -->  Plugin Dispatch  -->  Notifications
  (API)         (configurable       (exact, regex,         (Slack, Email,       (channels,
                 interval)           field-level)           Jira, SMS, ...)     tickets, etc.)
```

1. **Poll** - Fetches audit events from the PCE at a configurable interval (default: 10s)
2. **Match** - Each event is checked against watcher rules (exact type, regex patterns, field-level filters)
3. **Render** - Matched events are formatted through Jinja2 templates
4. **Dispatch** - Rendered notifications are sent to one or more output plugins
5. **Track** - Statistics are collected and available via the web dashboard and API

## Quick Start

### Install

```bash
pip install -e .
```

### Create a configuration file

```bash
pce-events config init --output config.yaml
```

This walks you through setting up the PCE connection interactively and creates a starter config with a catch-all watcher.

### Validate configuration

```bash
pce-events config validate --config config.yaml
```

### Run

```bash
pce-events run --config config.yaml
```

### Docker (quickstart - no config needed)

```bash
docker build -t pretty-cool-events .
mkdir -p config
docker run -v $(pwd)/config:/config -p 8443:8443 pretty-cool-events
```

Open `http://localhost:8443` and configure PCE credentials in the browser. Config is saved to `./config/config.yaml` and persists across restarts.

### Docker (with existing config)

```bash
docker run -v $(pwd)/config:/config -p 8443:8443 pretty-cool-events
```

## Configuration

Configuration is a YAML file with two main sections: `config` (connection and plugin settings) and `watchers` (event routing rules).

### Minimal Example

```yaml
config:
  pce: pce.example.com:8443
  pce_api_user: api_xxxxxxxxxxxx
  pce_api_secret: your-secret-here
  pce_org: 1
  pce_poll_interval: 10
  httpd: true
  httpd_listener_port: 8443
  default_template: default.html
  plugin_config:
    PCEStdout:
      prepend: "[PCE] "

watchers:
  ".*":
    - status: "*"
      plugin: PCEStdout
      extra_data:
        template: default.html
```

### Full Example

See [`config.yaml.example`](config.yaml.example) for a complete configuration with all plugins and watchers.

### Config Reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `pce` | string | *required* | PCE hostname (e.g. `pce.example.com:8443`) |
| `pce_api_user` | string | *required* | API key identifier (starts with `api_`) |
| `pce_api_secret` | string | *required* | API key secret |
| `pce_org` | int | `1` | PCE organization ID |
| `pce_poll_interval` | int | `10` | Seconds between event polls |
| `pce_traffic_interval` | int | `120` | Seconds between traffic flow queries |
| `httpd` | bool | `false` | Enable the web UI |
| `httpd_listener_address` | string | `0.0.0.0` | Web UI bind address |
| `httpd_listener_port` | int | `8443` | Web UI port |
| `default_template` | string | `default.html` | Default Jinja2 output template |
| `traffic_worker` | bool | `false` | Enable traffic flow analysis polling |

### Environment Variable Overrides

Secrets can be provided via environment variables instead of the config file:

| Variable | Overrides |
|----------|-----------|
| `PCE_EVENTS_PCE` | `config.pce` |
| `PCE_EVENTS_PCE_API_USER` | `config.pce_api_user` |
| `PCE_EVENTS_PCE_API_SECRET` | `config.pce_api_secret` |
| `PCE_EVENTS_PCE_ORG` | `config.pce_org` |
| `PCE_EVENTS_PCE_POLL_INTERVAL` | `config.pce_poll_interval` |

## Watchers

Watchers define which PCE events trigger which plugins. Each watcher has a **pattern** (the event type to match) and one or more **actions** (plugin + template + extra data).

### Pattern Matching

| Pattern | Matches |
|---------|---------|
| `user.login` | Exactly `user.login` |
| `user.*` | All user events (login, logout, create, etc.) |
| `rule_set.*` | Rule set create, update, delete |
| `agent.*` | All agent events (activate, tampering, deactivate, etc.) |
| `request.*` | Authentication failures, server errors |
| `.*` | Every event (catch-all) |

Exact patterns are checked first (O(1) hash lookup), then regex patterns are evaluated in order.

### Status Matching

| Status | Behavior |
|--------|----------|
| `success` | Only events with `status: success` |
| `failure` | Only events with `status: failure` |
| `*` or `any` | All events regardless of status (including null) |

Note: ~35% of PCE events have `null` status (e.g. session terminations, system tasks). Use `*` to catch these.

### Advanced Field Matching

Add `match_fields` to a watcher's `extra_data` to filter on any event field:

```yaml
watchers:
  ".*":
    - status: "*"
      plugin: PCESlack
      extra_data:
        template: default-slack.html
        channel: "#security-critical"
        match_fields:
          severity: "err|warning"                    # err OR warning
          created_by.user.username: "admin@.*"       # regex on nested field
```

Supported operators:

| Operator | Example | Description |
|----------|---------|-------------|
| Exact | `success` | Matches exactly |
| Wildcard | `*` | Matches any value including null |
| Negation | `!info` | Matches anything except `info` |
| Alternatives | `err\|warning` | Matches either value |
| Regex | `admin@.*` | Full regex matching |
| Dot notation | `created_by.user.username` | Access nested event fields |

### Watcher Examples

```yaml
watchers:
  # Catch-all: log everything to a file
  ".*":
    - status: "*"
      plugin: PCEFile
      extra_data:
        template: default-json.html

  # User logins to Slack
  user.login:
    - status: success
      plugin: PCESlack
      extra_data:
        template: default-slack.html
        channel: "#access-log"

  # Failed auth to PagerDuty
  request.authentication_failed:
    - status: failure
      plugin: PCEPagerDuty
      extra_data:
        template: sms.tmpl

  # All agent events to email
  agent.*:
    - status: "*"
      plugin: PCEMail
      extra_data:
        template: email.tmpl
        email_to: security-team@example.com

  # Critical events only (severity err or warning)
  ".*":
    - status: "*"
      plugin: PCESlack
      extra_data:
        template: default-slack.html
        channel: "#security-alerts"
        match_fields:
          severity: "err|warning"
```

## Throttling

Throttling prevents notification storms from high-frequency events. Set a default throttle that applies to all watchers, and optionally override per watcher.

### Default Throttle

Set in the config file or via the Configuration page:

```yaml
config:
  throttle_default: "1/1h"    # Max 1 notification per event_type per plugin per hour
```

Format: `N/period` where N is the max count and period is a duration:

| Spec | Meaning |
|------|---------|
| `1/1h` | Max 1 per hour (per event_type + plugin combo) |
| `5/1h` | Max 5 per hour |
| `10/24h` | Max 10 per day |
| `0/1h` | Suppress all (mute) |
| (empty) | No throttle (unlimited) |

### Per-Watcher Override

Add `throttle` to a watcher's `extra_data` to override the default:

```yaml
watchers:
  user.login:
    - status: failure
      plugin: PCESlack
      extra_data:
        template: default-slack.html
        channel: "#security"
        throttle: "1/1h"        # Only 1 failed login alert per hour

  agent.tampering:
    - status: "*"
      plugin: PCEPagerDuty
      extra_data:
        template: sms.tmpl
        throttle: "1/24h"       # Max 1 page per day for tampering
```

Throttle keys are `event_type:plugin` - so `user.login:PCESlack` and `user.login:PCEMail` are throttled independently.

### Monitoring Throttle State

- **Config page**: Shows live throttle status (active keys, suppressed counts)
- **API**: `GET /api/throttle` returns `{"default": "1/1h", "active_keys": 5, "total_suppressed": 23, "suppressed_by_key": {"user.login:PCESlack": 12, ...}}`

## Traffic Watchers

Traffic watchers monitor PCE traffic flows for specific patterns (blocked connections, unusual ports, cross-environment traffic) and send notifications. They use the PCE's async traffic analysis API with human-readable label expressions.

### Configuration

Traffic watchers are configured in a top-level `traffic_watchers` section:

```yaml
traffic_watchers:
  - name: blocked-to-payment-db
    src_include: "env=prod"
    dst_include: "app=payment, role=db"
    services_include: "3306/tcp, 5432/tcp"
    policy_decisions: [blocked, potentially_blocked]
    plugin: PCESlack
    template: default-slack.html
    interval: "24h"
    max_results: 500

  - name: cross-env-traffic
    src_include: "env=prod"
    dst_include: "env=staging"
    policy_decisions: [allowed, blocked, potentially_blocked]
    plugin: PCEMail
    template: email-full.html
    interval: "6h"
```

### Label Expressions

Traffic watchers use human-readable label expressions that auto-resolve to PCE label hrefs:

| Expression | Meaning |
|-----------|---------|
| `env=prod` | Workloads with env label = prod |
| `env=prod, bu=banking` | AND: both labels must match |
| `role=web OR role=db` | OR: either label matches |
| `env=dev, env=staging` (in exclude) | Exclude both dev and staging |

### Service Filters

| Expression | Meaning |
|-----------|---------|
| `443/tcp` | HTTPS |
| `3306/tcp, 5432/tcp` | MySQL or PostgreSQL |
| `53/udp` | DNS |
| `22/tcp` | SSH |
| (empty) | All services |

### Creating Traffic Watchers via the UI

1. Go to **Traffic** page, run a query with your desired filters
2. Find a flow you want to watch, click the **eye button**
3. The watcher builder pre-fills source/destination labels, port, protocol, and policy decision from that specific flow
4. Adjust the scope (broaden to all `env=prod` instead of one specific host)
5. Pick a plugin and check interval
6. Click "Create Traffic Watcher" - persisted to config immediately

### Traffic Watcher Fields

| Field | Description | Default |
|-------|------------|---------|
| `name` | Unique name for the watcher | *required* |
| `src_include` | Source label expression | (all) |
| `src_exclude` | Source labels to exclude | (none) |
| `dst_include` | Destination label expression | (all) |
| `dst_exclude` | Destination labels to exclude | (none) |
| `services_include` | Port/protocol filter | (all) |
| `services_exclude` | Services to exclude | (none) |
| `policy_decisions` | Which decisions to include | `[blocked, potentially_blocked]` |
| `plugin` | Plugin to notify | `PCEStdout` |
| `template` | Output template | `default.html` |
| `interval` | How often to check | `24h` |
| `max_results` | Max flows per check | `500` |

## Plugins

All plugins are configured under `config.plugin_config` in the config file. Only plugins referenced by watchers are activated at runtime.

### PCEStdout - Console Output

Prints rendered events to the application log. Useful for debugging and validation.

```yaml
PCEStdout:
  prepend: "[PCE] "
  append: ""
```

### PCESlack - Slack

Sends Block Kit formatted messages to Slack channels.

```yaml
PCESlack:
  slack_bot_token: xoxb-...
  template: default-slack.html
```

Requires a Slack App with the `chat:write` scope. Each watcher specifies the target channel in `extra_data.channel`.

### PCEMail - Email (SMTP)

Sends HTML email notifications via SMTP with TLS.

```yaml
PCEMail:
  smtp_host: smtp.example.com
  smtp_port: 587
  smtp_user: alerts@example.com
  smtp_password: secret
  email_from: alerts@example.com
  email_to: team@example.com
  template: email.tmpl
```

### PCESNS - SMS (AWS SNS)

Sends SMS text messages via Amazon SNS.

```yaml
PCESNS:
  access_key: AKIAXXXXXXXX
  access_key_secret: secret
  aws_region_name: us-east-1
```

Each watcher specifies the phone number in `extra_data.phone_number` (E.164 format: `+15551234567`).

### PCESyslog - Syslog

Forwards events to a remote syslog server. Supports UDP and TLS/TCP.

```yaml
PCESyslog:
  syslog_host: syslog.example.com
  syslog_port: 514
  syslog_cert_file: ""
  template: default.html
```

### PCEWebhook - Generic Webhook

POSTs event data to any URL. Universal integration point.

```yaml
PCEWebhook:
  url: https://hooks.example.com/events
  bearer_token: your-token
```

### PCEJira - Jira

Creates Jira issues from events.

```yaml
PCEJira:
  jira_server: https://mycompany.atlassian.net
  username: user@example.com
  api_token: secret
  project: SEC
  template: default.html
```

### PCETeams - Microsoft Teams

Sends messages via Teams Incoming Webhook.

```yaml
PCETeams:
  webhook: https://outlook.office.com/webhook/...
  template: default-teams.tmpl
```

### PCEServiceNow - ServiceNow

Creates incidents in ServiceNow.

```yaml
PCEServiceNow:
  instance: mycompany.service-now.com
  username: admin
  password: secret
  template: default.html
```

### PCEPagerDuty - PagerDuty

Creates PagerDuty incidents to page on-call.

```yaml
PCEPagerDuty:
  api_key: your-api-key
  pd_from: oncall@example.com
  pd_service: PXXXXXX
  pd_priority: PXXXXXX
  template: sms.tmpl
```

Use the `pd` CLI to find service and priority IDs: `pd incident create --debug -t "Test" --service "Illumio" --priority=P1`

### PCEFile - File Logger

Appends rendered events to a local file.

```yaml
PCEFile:
  logfile: events.log
  template: default-json.html
```

## Templates

Events are formatted through Jinja2 templates before dispatch. Templates have access to all event fields as top-level variables and also as a nested `event` object.

| Template | Format | Best For |
|----------|--------|----------|
| `default.html` | Plain text | Console output, general use |
| `default-slack.html` | Slack Block Kit JSON | Slack messages |
| `default-json.html` | JSON | File logging, webhooks |
| `email.tmpl` | HTML | Email notifications |
| `sms.tmpl` | Short text | SMS, PagerDuty |
| `default-teams.tmpl` | Markdown | Microsoft Teams |
| `rule_set.create.jira.tmpl` | Text | Jira tickets for rule set changes |

### Template Variables

All event fields are available as top-level variables:

```
{{ event_type }}              - e.g. "user.login"
{{ status }}                  - "success", "failure", or null
{{ severity }}                - "info", "warning", "err"
{{ timestamp }}               - ISO 8601 timestamp
{{ pce_fqdn }}                - PCE hostname
{{ href }}                    - Event API path
{{ created_by }}              - Dict with user/system/agent info
{{ action }}                  - Dict with API endpoint, method, status code
{{ resource_changes }}        - List of resource change dicts
{{ notifications }}           - List of notification dicts
```

The full event is also available as `{{ event }}` for nested access: `{{ event.created_by.user.username }}`.

### Writing Custom Templates

Place `.html` or `.tmpl` files in the `pretty_cool_events/templates/` directory. Reference them by filename in watcher `extra_data.template`.

## Web UI

Enable with `httpd: true` in the config. The web interface provides:

| Page | Path | Description |
|------|------|-------------|
| Dashboard | `/` | Live stats (events received, matched, plugin activity) |
| Configuration | `/config` | Edit PCE connection settings |
| Plugins | `/plugins` | Enable/disable plugins, configure credentials, see setup instructions |
| Watchers | `/watchers` | Add, view, and delete watcher rules |
| Events | `/events` | Browse historical PCE events with time range picker and filters |
| Statistics | `/statistics` | Charts (plugin activity, event distribution, timeline) |
| Guide | `/guide` | How-it-works documentation, pattern reference, CLI help |

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check (`{"status": "ok"}`) |
| `/api/stats` | GET | Current statistics as JSON |
| `/api/events` | GET | Fetch PCE events with time range and filters |

#### `/api/events` Query Parameters

| Parameter | Example | Description |
|-----------|---------|-------------|
| `since` | `24h`, `7d`, `2026-01-01T00:00:00Z` | Start time (relative or ISO) |
| `until` | `2026-01-02T00:00:00Z` | End time (default: now) |
| `max_results` | `500` | Maximum events to return |
| `event_type` | `user.*` | Filter by event type (regex) |
| `status` | `success`, `failure`, `null` | Filter by status |
| `severity` | `info`, `warning`, `err` | Filter by severity |
| `created_by` | `user`, `system`, `agent` | Filter by creator type |
| `search` | `admin@illumio` | Free-text search across all fields |

## CLI Reference

```
pce-events run --config config.yaml [--log-level DEBUG|INFO|WARNING|ERROR]
    Start the event monitoring service.

pce-events config init [--output config.yaml]
    Create a new config file interactively.

pce-events config validate --config config.yaml
    Validate a config file and show summary.

pce-events config show --config config.yaml
    Display config with secrets masked.

pce-events watcher list --config config.yaml
    List all configured watchers in a table.

pce-events watcher add --config config.yaml
    Add a new watcher interactively.

pce-events test-plugin <PLUGIN_NAME> --config config.yaml
    Send a synthetic test event through a plugin.
```

## Project Structure

```
pretty_cool_events/
  __init__.py              Package init
  __main__.py              python -m entry point
  cli.py                   Click CLI (run, config, watcher, test-plugin)
  config.py                Pydantic v2 config models, load/save, validation
  pce_client.py            httpx-based PCE API client
  event_loop.py            Main polling loop with graceful shutdown
  watcher.py               Flexible event matching (exact, regex, field-level)
  stats.py                 Thread-safe statistics tracking
  plugin_meta.py           Plugin descriptions, field labels, setup instructions
  plugins/
    base.py                ABC base class with auto-registration and template rendering
    stdout.py              Console output
    slack.py               Slack (slack_sdk)
    email.py               SMTP email
    sns.py                 AWS SNS SMS
    syslog.py              Remote syslog (UDP/TLS)
    webhook.py             Generic HTTP webhook (httpx)
    jira_plugin.py         Jira issue creation
    teams.py               Microsoft Teams webhook (httpx)
    servicenow.py          ServiceNow incidents (httpx)
    pagerduty.py           PagerDuty incidents (pdpyras)
    file.py                File logger
  data/
    event_types.yaml       Catalog of 273 PCE event types
  templates/               Jinja2 output templates
  web/
    app.py                 Flask app factory
    routes.py              Blueprint with all routes and API
    templates/             Bootstrap 5 web UI templates
    static/                CSS, JS, images
tests/
  conftest.py              Shared fixtures
  test_config.py           Config loading, validation, env overrides (11 tests)
  test_watcher.py          Pattern matching, status, field filters (14 tests)
  test_stats.py            Thread-safe counters, timeline cap (5 tests)
  test_pce_client.py       HTTP mocking, health check, events (5 tests)
  test_event_loop.py       Routing, shutdown, error recovery (4 tests)
  test_cli.py              CLI commands via CliRunner (4 tests)
  test_plugins/            Per-plugin tests (7 tests)
  test_web/test_routes.py  Flask route tests (12 tests)
  integration/             End-to-end pipeline test (1 test)
```

## Development

### Setup

```bash
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest                         # 62 tests
pytest --cov=pretty_cool_events  # with coverage
```

### Lint

```bash
ruff check pretty_cool_events/
```

### Type Check

```bash
mypy pretty_cool_events/
```

## Dependencies

### Runtime

| Package | Purpose |
|---------|---------|
| Flask | Web UI |
| httpx | PCE API client, webhook/Teams/ServiceNow HTTP calls |
| Pydantic v2 | Config validation |
| Click | CLI |
| Rich | CLI tables and formatting |
| Jinja2 | Template rendering |
| PyYAML | Config file parsing |
| slack_sdk | Slack API |
| boto3 | AWS SNS (SMS) |
| jira | Jira API |
| pdpyras | PagerDuty API |

### Removed (from original)

| Package | Replaced By |
|---------|-------------|
| `straight.plugin` | `importlib` + `__init_subclass__` auto-registration |
| `rest3client` | `httpx` |
| `regex` | `re` (stdlib) |
| `jsonpickle` | Not needed |
| `pymsteams` | Direct `httpx` POST |

## Docker

```bash
# Build
docker build -t pretty-cool-events .

# First run (no config - bootstrap mode)
mkdir -p config
docker run -v $(pwd)/config:/config -p 8443:8443 pretty-cool-events
# -> Web UI starts at http://localhost:8443, configure via browser
# -> Config saved to ./config/config.yaml, persists across restarts

# Run with existing config
docker run -v $(pwd)/config:/config -p 8443:8443 pretty-cool-events

# With environment variable overrides for PCE credentials
docker run -v $(pwd)/config:/config -p 8443:8443 \
  -e PCE_EVENTS_PCE=pce.example.com:8443 \
  -e PCE_EVENTS_PCE_API_USER=api_xxx \
  -e PCE_EVENTS_PCE_API_SECRET=secret \
  pretty-cool-events

# Override log level
docker run -v $(pwd)/config:/config -p 8443:8443 pretty-cool-events \
  pce-events run --config /config/config.yaml --log-level DEBUG
```

Mount the `/config` directory (not just the file) so config backups can be created alongside the config file. The Dockerfile uses a multi-stage build with Python 3.12.

## CI/CD

GitHub Actions workflow (`.github/workflows/main.yml`) runs on every push to `main` and PRs:

1. **Test** - `pip install`, `ruff check`, `pytest --cov`
2. **Build & Push** - Docker image to `ghcr.io` (only on `release` branch)

## Known Issues

- Python creates SSL warnings with untrusted certificates. Set `export PYTHONWARNINGS="ignore:Unverified HTTPS request"` or set `verify_tls: false` in config.
- The traffic worker is experimental and partially implemented.
- Web UI config changes are in-memory only; restart the service to persist from the config file.

## License

MIT
