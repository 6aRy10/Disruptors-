#!/bin/sh
# Dispatch one image to three roles. Never prints environment variables.
set -eu

ROLE="${HERMES_ROLE:-api}"
PORT="${PORT:-8000}"

case "$ROLE" in
  api)
    exec python -m uvicorn dependency.api.main:app \
      --host 0.0.0.0 --port "$PORT" --proxy-headers --no-server-header
    ;;
  publisher)
    exec python scripts/run_kafka_publisher.py --heartbeat "${HERMES_HEARTBEAT_FILE:-/app/run/heartbeat}"
    ;;
  consumer)
    exec python scripts/run_kafka_consumer.py --heartbeat "${HERMES_HEARTBEAT_FILE:-/app/run/heartbeat}" \
      ${HERMES_CONSUMER_EXTRA_ARGS:-}
    ;;
  *)
    echo "Unknown HERMES_ROLE '$ROLE'. Use api, publisher or consumer." >&2
    exit 64
    ;;
esac
