# Build stage
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY pretty_cool_events/ pretty_cool_events/

RUN pip install --no-cache-dir .

# Runtime stage
FROM python:3.12-slim

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
