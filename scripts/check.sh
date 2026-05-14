#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${REDIS_PORT:-6390}"
STARTED_REDIS=0
MASTER_KEY="${POA_MASTER_KEY:-1111111111111111111111111111111111111111111111111111111111111111}"

cleanup() {
  if [[ "$STARTED_REDIS" -eq 1 ]]; then
    redis-cli -p "$PORT" shutdown nosave >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required for the local PR validation gate." >&2
    exit 1
  fi
}

require_cmd uv
require_cmd npm

echo "Running no-service CLI smoke tests..."
uv run --python 3.11 --extra dev pytest tests/test_cli_smoke.py -q

if ! command -v redis-cli >/dev/null 2>&1 || ! command -v redis-server >/dev/null 2>&1; then
  echo "redis-cli and redis-server are required for service-backed validation." >&2
  echo "Install Redis, or run the no-service subset:" >&2
  echo "  PYTHONPATH=src python3 -m pytest tests/test_cli_smoke.py tests/test_agent.py tests/test_crypto.py" >&2
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

echo "Verifying Chainguard base digest pins..."
grep -q "$(awk '$1=="latest"{print $2}' .chainguard-digest)" Dockerfile \
  || { echo "Dockerfile runtime digest drifted from .chainguard-digest" >&2; exit 1; }
grep -q "$(awk '$1=="latest-dev"{print $2}' .chainguard-digest)" Dockerfile \
  || { echo "Dockerfile builder digest drifted from .chainguard-digest" >&2; exit 1; }

echo "Running service-backed privacy boundary tests..."
POA_LLM=template POA_MASTER_KEY="$MASTER_KEY" REDIS_PORT="$PORT" \
  uv run --python 3.11 --extra dev pytest tests/test_boundary.py tests/test_crypto.py -q

echo "Running canonical dashboard lint and build..."
(
  cd deploy/dashboard
  npm ci
  npm run lint
  npm run build
)
