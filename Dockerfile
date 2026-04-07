# Build stage
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY pretty_cool_events/ pretty_cool_events/

RUN pip install --no-cache-dir .

# Runtime stage
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Pretty Cool Events"
LABEL org.opencontainers.image.description="Real-time event monitoring and notification system for Illumio PCE. Polls PCE audit events, matches against configurable watchers, and routes to Slack, Email, PagerDuty, Jira, Teams, ServiceNow, SMS, webhooks, and more. Includes web UI for configuration, event browsing, traffic flow analysis, and live dashboards."
LABEL org.opencontainers.image.url="https://github.com/alexgoller/illumio-pretty-cool-events"
LABEL org.opencontainers.image.source="https://github.com/alexgoller/illumio-pretty-cool-events"
LABEL org.opencontainers.image.documentation="https://github.com/alexgoller/illumio-pretty-cool-events#readme"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/pce-events /usr/local/bin/pce-events
COPY pretty_cool_events/ pretty_cool_events/

ENV PYTHONWARNINGS="ignore:Unverified HTTPS request"

# Mount /config as a volume for persistent config + backups
VOLUME ["/config"]

EXPOSE 8443

# If /config/config.yaml exists, use it. Otherwise bootstrap with web UI.
ENTRYPOINT ["pce-events", "run", "--config", "/config/config.yaml"]
