#!/usr/bin/env bash
# 60-second reproducible demo. Runs the adversarial fixture end-to-end and
# prints four externally-verifiable proofs:
#   1. Redis ACL: public client rejected when writing to private keyspace
#   2. Agent run: boundary crossing with planted PII (SSN, API key, phone…)
#   3. Leak scan: 0 hits of 131+ fingerprints in cited.md
#   4. Guild session URL + dashboard URL
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
REDIS_PORT="${REDIS_PORT:-6390}"
REDIS_PUB_PW="${REDIS_PUB_PW:-pubpw}"

# Phase G6: when POA_REDIS_TLS=on, all redis-cli probes go over mTLS.
# Agent process itself picks this up via stores/private_store.py.
RCLI_TLS=()
if [[ "${POA_REDIS_TLS:-off}" == "on" ]]; then
  RCLI_TLS=(
    --tls
    --cacert "${POA_REDIS_TLS_CA:-private/tls/ca.crt}"
    --cert  "${POA_REDIS_TLS_CERT:-private/tls/agent.crt}"
    --key   "${POA_REDIS_TLS_KEY:-private/tls/agent.key}"
  )
fi

export POA_FIXTURE="fixtures/adversarial_threads.json"
export POA_INSFORGE_URL="${POA_INSFORGE_URL:-https://q7haa32f.us-east.insforge.app}"
export POA_INSFORGE_EMAIL="${POA_INSFORGE_EMAIL:-demo@proof-of-action.local}"
export POA_INSFORGE_PASSWORD="${POA_INSFORGE_PASSWORD:-demoPass!ProofOfAction2026}"

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
dim()   { printf "\033[2m%s\033[0m\n" "$*"; }
ok()    { printf "\033[32m%s\033[0m\n" "$*"; }
fail()  { printf "\033[31m%s\033[0m\n" "$*"; }
hr()    { printf "\033[2m%s\033[0m\n" "────────────────────────────────────────────────────────────────────────"; }

hr
bold "Proof-of-Action — adversarial demo"
dim  "fixture: $POA_FIXTURE"
hr

# ────────────────────────────────────────────────────────────────────────
bold "[1/4] Redis ACL — public client tries cross-zone private write"
hr
set +e
OUT=$(redis-cli -p "$REDIS_PORT" --user agent_public -a "$REDIS_PUB_PW" \
        --no-auth-warning SET private:sneaky boom 2>&1)
set -e
echo "  $ redis-cli --user agent_public SET private:sneaky boom"
echo "  → $OUT"
if echo "$OUT" | grep -qi "noperm\|no permission"; then
  ok   "  ✓ infrastructure-layer boundary held: NOPERM from Redis itself"
else
  fail "  ✗ expected NOPERM, got: $OUT"
  exit 1
fi

# ────────────────────────────────────────────────────────────────────────
hr
bold "[2/4] Agent run against adversarial fixture (planted SSN, API key, phone)"
hr
"$PYTHON" -m proof_of_action.agent | sed 's/^/  /'

# ────────────────────────────────────────────────────────────────────────
hr
bold "[3/4] Leak scan — scanning cited.md for 131+ private fingerprints"
hr
"$PYTHON" - <<'PY' | sed 's/^/  /'
import sys
from proof_of_action import agent
from proof_of_action.redaction import private_fingerprints, scan_for_leaks
from proof_of_action.stores import private_store
from scripts import publish

ctxs = agent.load_fixture()
drafts = private_store.all_drafts()

fps = private_fingerprints(ctxs, drafts)
md = publish.build_cited_md()
leaks = scan_for_leaks(md, fps)

print(f"fingerprints scanned: {len(fps)}")
print(f"leaks detected: {len(leaks)}")
if leaks:
    print("FAIL — leaks:", leaks[:5])
    sys.exit(1)
print("✓ clean: zero private substrings in cited.md")
PY

# ────────────────────────────────────────────────────────────────────────
hr
bold "[4/4] External audit + dashboard"
hr
IFC="${IFC:-/Users/jwalinshah/.npm/_npx/d7c0f92b98ce1c29/node_modules/.bin/insforge}"
if [[ -x "$IFC" ]]; then
  echo "  Last Guild session:"
  $IFC db query "SELECT guild_url FROM guild_sessions ORDER BY created_at DESC LIMIT 1" 2>&1 \
    | grep -Eo "https://[^│ ]+" | head -1 | sed 's/^/    → /'
  echo
  echo "  Last boundary crossing:"
  $IFC db query "SELECT projection_type, private_field_count, public_field_count, leak_check_passed FROM boundary_crossings ORDER BY created_at DESC LIMIT 1" 2>&1 \
    | tail -5 | sed 's/^/    /'
fi

echo
bold "Dashboard: https://q7haa32f.insforge.site  (hosted — sign in as $POA_INSFORGE_EMAIL)
  Local dev:  cd dashboard && npm run dev  →  http://localhost:5173"
hr
ok "Demo complete."
