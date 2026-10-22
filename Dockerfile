# HERMES backend image: API, Kafka outbox publisher and Kafka consumer share it.
# Select the role with HERMES_ROLE (api | publisher | consumer); see docker/entrypoint.sh.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system hermes && useradd --system --gid hermes --home /app hermes

WORKDIR /app

# Install dependencies first so source edits do not invalidate the wheel layer.
COPY pyproject.toml requirements.txt ./
RUN pip install -r requirements.txt

# Modules resolve the repo root relative to src/, so keep the layout instead of
# installing into site-packages.
COPY src ./src
COPY scripts ./scripts
COPY web ./web
COPY sql ./sql
COPY data ./data
COPY docker/entrypoint.sh /usr/local/bin/hermes-entrypoint
RUN chmod +x /usr/local/bin/hermes-entrypoint \
    && mkdir -p /app/run && chown -R hermes:hermes /app

USER hermes

# Secrets (database URL, Kafka credentials, write token) are injected at runtime only.
ENV PYTHONPATH=/app/src \
    HERMES_ROLE=api \
    PORT=8000 \
    HERMES_HEARTBEAT_FILE=/app/run/heartbeat \
    DEPENDENCY_DATABASE_TARGET=aiven \
    AIVEN_KAFKA_ROUTING_MODE=single \
    AIVEN_KAFKA_PHYSICAL_TOPIC=dependency.events

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["sh", "-c", "python scripts/healthcheck.py \"$HERMES_ROLE\""]

ENTRYPOINT ["hermes-entrypoint"]
