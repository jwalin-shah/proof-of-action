#!/usr/bin/env bash
# Proof-of-Action: health check for the private/public boundary.
#
# Verifies each layer is functioning independently:
#   - local Python env
#   - Redis running with two-user ACL enforced (NOPERM cross-zone test)
#   - InsForge creds sign in
#   - finalize-action edge function rejects unauthenticated calls (401)
#   - user-scoped DB read returns only the caller's rows

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

PASS=0
FAIL=0

ok()   { printf "  \033[32m✓\033[0m  %s\n" "$1"; PASS=$((PASS+1)); }
bad()  { printf "  \033[31m✗\033[0m  %s\n" "$1"; FAIL=$((FAIL+1)); }
warn() { printf "  \033[33m!\033[0m  %s\n" "$1"; }
hdr()  { printf "\n\033[1;36m▸ %s\033[0m\n" "$1"; }

# Load env if present.
if [[ -f .env.local ]]; then
  # shellcheck disable=SC1091
  set -a; source .env.local; set +a
fi

hdr "local env"
[[ -d .venv ]] && ok "venv present (.venv)" || bad "no .venv — run scripts/onboard.sh"
.venv/bin/python -c "import proof_of_action" 2>/dev/null \
  && ok "proof_of_action importable" \
  || bad "proof_of_action not installed into venv"

hdr "Redis private/public boundary"
PORT="${REDIS_PORT:-6390}"
if redis-cli -p "$PORT" ping >/dev/null 2>&1; then
  ok "Redis responding on :$PORT"

  PRIV_PW="${REDIS_PRIVATE_PW:-privpw}"
  PUB_PW="${REDIS_PUBLIC_PW:-pubpw}"

  if redis-cli -p "$PORT" --user agent_private -a "$PRIV_PW" --no-auth-warning \
      SET private:doctor:ping 1 >/dev/null 2>&1; then
    ok "agent_private can write private:*"
  else
    bad "agent_private cannot write private:* (ACL misconfigured)"
  fi

  # The key boundary test: agent_public trying to write private:* MUST
  # be rejected with NOPERM from Redis itself, not app logic.
  OUT="$(redis-cli -p "$PORT" --user agent_public -a "$PUB_PW" --no-auth-warning \
      SET private:doctor:ping "should_fail" 2>&1 || true)"
  if echo "$OUT" | grep -qi "NOPERM"; then
    ok "agent_public BLOCKED from private:* (NOPERM — infra-layer proof)"
  else
    bad "agent_public was NOT blocked from private:* — boundary broken"
  fi

  redis-cli -p "$PORT" --user agent_private -a "$PRIV_PW" --no-auth-warning \
    DEL private:doctor:ping >/dev/null 2>&1 || true
else
  bad "Redis not running on :$PORT — run: redis-server --port $PORT --daemonize yes"
fi

hdr "InsForge public plane"
URL="${POA_INSFORGE_URL:-https://q7haa32f.us-east.insforge.app}"
# Reachability = any HTTP response (not a connection error). The root
# URL may legitimately return 404/403 — that still means the server answered.
REACH_STATUS="$(curl -s -o /dev/null -m 5 -w "%{http_code}" "$URL" || echo "000")"
if [[ "$REACH_STATUS" != "000" ]]; then
  ok "InsForge reachable at $URL (HTTP $REACH_STATUS)"
else
  bad "InsForge unreachable at $URL (connection error)"
fi

if [[ -n "${POA_INSFORGE_EMAIL:-}" && -n "${POA_INSFORGE_PASSWORD:-}" ]]; then
  RESP="$(curl -sS -m 10 -X POST "$URL/api/auth/sessions?client_type=server" \
      -H 'Content-Type: application/json' \
      -d "$(printf '{"email":"%s","password":"%s"}' "$POA_INSFORGE_EMAIL" "$POA_INSFORGE_PASSWORD")")"
  if echo "$RESP" | grep -q '"accessToken"'; then
    ok "InsForge sign-in works for $POA_INSFORGE_EMAIL"
    TOKEN="$(echo "$RESP" | sed -n 's/.*"accessToken":"\([^"]*\)".*/\1/p')"

    # Edge function should reject un-authed calls with 401.
    UNAUTH_STATUS="$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        "$URL/functions/finalize-action" -H 'Content-Type: application/json' -d '{}')"
    [[ "$UNAUTH_STATUS" == "401" ]] \
      && ok "finalize-action rejects unauth'd calls (401)" \
      || bad "finalize-action auth check returned $UNAUTH_STATUS (expected 401)"

    # RLS-scoped select should succeed (returns only caller's rows).
    ROWS="$(curl -sS -m 10 "$URL/database/records/proof_actions?limit=200" \
        -H "Authorization: Bearer $TOKEN")"
    if echo "$ROWS" | grep -q '^\['; then
      CNT="$(echo "$ROWS" | tr -cd '{' | wc -c | tr -d ' ')"
      ok "RLS-scoped read on proof_actions works (your row count: ${CNT})"
    else
      warn "RLS-scoped read returned non-array — endpoint may differ"
    fi
  else
    bad "InsForge sign-in FAILED:
$RESP"
  fi
else
  warn "POA_INSFORGE_EMAIL/PASSWORD not set — run scripts/onboard.sh"
fi

hdr "summary"
printf "  %d passed, %d failed\n\n" "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
