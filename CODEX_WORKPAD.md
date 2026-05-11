# MAX-251 Workpad

## Issue

- Linear: `MAX-251`
- Title: Proof-of-Action: require boundary, leak, ACL, lint, and dashboard CI
- Repo: `/Users/jwalinshah/projects/apps/proof-of-action`
- Worktree: `/Users/jwalinshah/projects/apps/proof-of-action-MAX-251`
- Branch: `codex/MAX-251-poa-boundary-ci`
- Base: `origin/main` at `2da7e87`

## Plan

- Add PR CI for Python privacy boundary validation, including leak and Redis ACL tests.
- Run Python lint in the same boundary workflow.
- Build and lint the canonical hosted dashboard under `deploy/dashboard`.
- Document `deploy/dashboard` as canonical and root `dashboard/` as legacy/local reference.

## Validation

```bash
uv run --python 3.11 --extra dev ruff check .
```

Result: passed.

```bash
PORT=6391
redis-server --port "$PORT" --daemonize yes --save "" --appendonly no
REDIS_PORT="$PORT" bash scripts/setup_redis.sh
POA_LLM=template POA_MASTER_KEY=1111111111111111111111111111111111111111111111111111111111111111 \
  REDIS_PORT="$PORT" uv run --python 3.11 --extra dev pytest tests/test_boundary.py tests/test_crypto.py -q
redis-cli -p "$PORT" shutdown nosave
```

Result: passed, 7 passed.

```bash
cd deploy/dashboard && npm ci
```

Result: passed.

```bash
cd deploy/dashboard && npm run lint
```

Result: passed.

```bash
cd deploy/dashboard && npm run build
```

Result: passed.

```bash
git diff --check
```

Result: passed.

## Handoff

Pending PR.
