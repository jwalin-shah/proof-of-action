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

GitHub PR CI after first push:

- `Privacy boundary, leak, ACL, and Python lint`: passed.
- `Canonical dashboard lint and build`: passed.
- Existing `build-scan-sign`: failed on Grype high-or-critical CVE threshold.

Follow-up in this branch:

```bash
bash scripts/pin-chainguard.sh
```

Result: refreshed Chainguard `latest` and `latest-dev` base image digests in
`Dockerfile` and `.chainguard-digest`.

```bash
RUNTIME=$(awk '$1=="latest"{print $2}' .chainguard-digest)
BUILDER=$(awk '$1=="latest-dev"{print $2}' .chainguard-digest)
grep -q "$RUNTIME" Dockerfile
grep -q "$BUILDER" Dockerfile
```

Result: passed.

Local Docker validation was not available because `docker` is not installed in
this environment; GitHub CI will rerun the image build and Grype scan after
push.

## Handoff

Pending PR.

---

# WP-066 Workpad

## Task

- Objective: Deepen one shallow module by moving scattered caller knowledge
  behind a smaller interface.
- Branch: `codex/WP-066-shallow-module-deepening`
- Owned surface: `src/proof_of_action/boundary_verifier.py`,
  `src/proof_of_action/agent.py`, and `tests/test_agent.py`.

## Change

- Added `BoundaryCrossing` as the boundary verifier's module-owned description
  of a public/private crossing.
- Changed `BoundaryVerifier.verify` to accept one `BoundaryCrossing` instead of
  repeated caller flags and ordered inputs.
- Updated agent orchestration and focused tests to use
  `BoundaryCrossing.public_artifact(...)`, so action id, projection type, and
  default step are derived inside `boundary_verifier.py`.

## Validation

```bash
uv run --python 3.11 --extra dev pytest tests/test_agent.py tests/test_projection_registry.py -q
```

Result: passed, 10 passed.

```bash
uv run --python 3.11 --extra dev ruff check . && bash scripts/check.sh && git diff --check
```

Result: passed. `scripts/check.sh` ran service-backed Redis privacy boundary
tests, canonical dashboard lint, and canonical dashboard build.

## Residual Risk

- `BoundaryCrossing.public_artifact(...)` covers the currently exercised
  `PublicArtifactView` crossing only. The existing `ProjectionType` literals for
  `OpenhumanView` and `VapiView` remain unchanged, but they do not yet have
  dedicated verifier constructors because no direct verifier caller currently
  sends those views.
