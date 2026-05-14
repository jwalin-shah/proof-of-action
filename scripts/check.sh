#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${REDIS_PORT:-6390}"
STARTED_REDIS=0

cleanup() {
  if [[ "$STARTED_REDIS" -eq 1 ]]; then
    redis-cli -p "$PORT" shutdown nosave >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if ! command -v redis-cli >/dev/null 2>&1 || ! command -v redis-server >/dev/null 2>&1; then
  echo "redis-cli and redis-server are required for service-backed validation." >&2
  echo "Install Redis, or run the no-service subset:" >&2
  echo "  PYTHONPATH=src python3 -m pytest tests/test_agent.py tests/test_crypto.py" >&2
  exit 1
fi

if ! redis-cli -p "$PORT" ping >/dev/null 2>&1; then
  redis-server --port "$PORT" --daemonize yes --save "" --appendonly no
  STARTED_REDIS=1
  for _ in 1 2 3 4 5; do
    redis-cli -p "$PORT" ping >/dev/null 2>&1 && break
    sleep 0.2
  done
fi

if ! redis-cli -p "$PORT" ping >/dev/null 2>&1; then
  echo "Redis did not start on localhost:$PORT" >&2
  exit 1
fi

REDIS_PORT="$PORT" bash scripts/setup_redis.sh >/dev/null

PYTHONPATH=src POA_LLM=template python3 -m pytest
