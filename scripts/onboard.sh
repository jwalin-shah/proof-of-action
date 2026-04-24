#!/usr/bin/env bash
# Proof-of-Action: one-command onboarding for a new self-hosting operator.
#
# Walks through: dep check → Redis up → ACL setup → InsForge creds →
# local .env.local write → smoke test. Idempotent — safe to re-run.
#
# Gmail OAuth is handled separately by the inbox daemon and is optional
# for the first-run fixture-based demo.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

bold()   { printf "\033[1m%s\033[0m\n" "$*"; }
dim()    { printf "\033[2m%s\033[0m\n" "$*"; }
green()  { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*" >&2; }
step()   { printf "\n\033[1;36m▸ %s\033[0m\n" "$*"; }

fail() { red "$*"; exit 1; }

require() {
  local cmd="$1" install_hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    fail "missing dependency: $cmd — install with: $install_hint"
  fi
  green "  ✓ $cmd"
}

prompt() {
  local label="$1" default="${2:-}"
  local value
  if [[ -n "$default" ]]; then
    read -r -p "$label [$default]: " value
    echo "${value:-$default}"
  else
    read -r -p "$label: " value
    echo "$value"
  fi
}

prompt_secret() {
  local label="$1"
  local value
  read -r -s -p "$label: " value
  echo >&2
  echo "$value"
}

echo
bold "Proof-of-Action — self-host onboarding"
dim "  sets up the private plane on this Mac + links it to an InsForge public plane"

# ─── 1. Dependency check ──────────────────────────────────────────────────
step "1/5  checking dependencies"
require python3       "brew install python@3.11"
require uv            "brew install uv   (or: curl -LsSf https://astral.sh/uv/install.sh | sh)"
require redis-server  "brew install redis"
require redis-cli     "brew install redis"
require node          "brew install node"
require curl          "brew install curl"

# ─── 2. Python env ────────────────────────────────────────────────────────
step "2/5  installing Python deps"
if [[ ! -d .venv ]]; then
  uv venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
uv pip install -e . >/dev/null
green "  ✓ venv + deps ready"

# ─── 3. Redis private plane ──────────────────────────────────────────────
step "3/5  starting local Redis (private plane, port 6390)"
REDIS_PORT="${REDIS_PORT:-6390}"
if ! redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1; then
  yellow "  Redis not running on $REDIS_PORT — starting in background"
  redis-server --port "$REDIS_PORT" --daemonize yes --save "" --appendonly no
  sleep 1
  redis-cli -p "$REDIS_PORT" ping >/dev/null || fail "failed to start Redis"
fi
REDIS_PORT="$REDIS_PORT" bash scripts/setup_redis.sh >/dev/null
green "  ✓ Redis + two-user ACL (agent_private / agent_public) configured"

# ─── 4. InsForge credentials ─────────────────────────────────────────────
step "4/5  linking InsForge public plane"

ENV_FILE=".env.local"
if [[ -f "$ENV_FILE" ]] && grep -q "POA_INSFORGE_EMAIL" "$ENV_FILE" 2>/dev/null; then
  green "  ✓ $ENV_FILE already has InsForge creds — skipping"
else
  cat <<'EOF'

  Sign up for a user account on the hosted Proof-of-Action dashboard:

    → https://q7haa32f.insforge.site

  Click "continue with Google" (or sign up with email). You can stop
  after signup — the password/email is what we need below.

  (RLS on the InsForge project means you only ever see your own rows.
   Your private data never goes near the hosted plane.)
EOF
  echo
  INS_EMAIL="$(prompt 'InsForge email')"
  INS_PASSWORD="$(prompt_secret 'InsForge password')"
  INS_URL="$(prompt 'InsForge URL' 'https://q7haa32f.us-east.insforge.app')"

  # Verify creds work.
  RESP="$(curl -sS -X POST "$INS_URL/api/auth/sessions?client_type=server" \
      -H 'Content-Type: application/json' \
      -d "$(printf '{"email":"%s","password":"%s"}' "$INS_EMAIL" "$INS_PASSWORD")")"
  if ! echo "$RESP" | grep -q '"accessToken"'; then
    fail "could not sign in to InsForge:
$RESP"
  fi
  green "  ✓ InsForge auth verified"

  # Append to env file without clobbering existing keys.
  {
    echo "# Proof-of-Action — written by scripts/onboard.sh"
    echo "POA_INSFORGE_URL=$INS_URL"
    echo "POA_INSFORGE_EMAIL=$INS_EMAIL"
    echo "POA_INSFORGE_PASSWORD=$INS_PASSWORD"
  } >> "$ENV_FILE"
  green "  ✓ wrote $ENV_FILE (gitignored)"
fi

# ─── 5. Optional Gmail OAuth ─────────────────────────────────────────────
step "5/6  Gmail OAuth (optional — skip to use fixtures first)"

GMAIL_TOKEN="$HOME/.config/proof-of-action/gmail-token.json"
if [[ -f "$GMAIL_TOKEN" ]]; then
  green "  ✓ Gmail token already present at $GMAIL_TOKEN — skipping"
elif [[ ! -f credentials.json ]]; then
  yellow "  credentials.json not found — create a GCP OAuth client (Desktop type),"
  yellow "  download as credentials.json, then run: .venv/bin/python scripts/onboard.py"
else
  cat <<'EOF'

  The next step opens Google in your browser. You'll consent to Gmail
  read-only access for your own account. The refresh token will live at
  ~/.config/proof-of-action/gmail-token.json on THIS Mac only — it is
  never uploaded to the public plane.

  If you see "Google hasn't verified this app", either:
    a) You're not on the test-user allowlist — ask the repo owner to add you, or
    b) Click 'Advanced → Go to Proof-of-Action (unsafe)' — safe because this
       is the app you just cloned; the warning is Google saying the GCP
       project isn't verified, not that anything malicious is happening.

EOF
  read -r -p "  Connect Gmail now? [y/N]: " CONNECT
  if [[ "$CONNECT" =~ ^[yY]$ ]]; then
    .venv/bin/python scripts/onboard.py || yellow "  Gmail OAuth skipped (you can re-run later)"
  else
    dim "  skipped. Run later with: .venv/bin/python scripts/onboard.py"
  fi
fi

# ─── 6. Smoke test ───────────────────────────────────────────────────────
step "6/6  smoke test — running agent end-to-end"

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

if [[ -f "$GMAIL_TOKEN" ]]; then
  dim "  Gmail token present — running against real inbox (last 5 threads)"
  POA_SOURCE=gmail POA_GMAIL_MAX=5 .venv/bin/python -m proof_of_action.agent
else
  dim "  no Gmail token — running against fixtures/sample_threads.json"
  .venv/bin/python -m proof_of_action.agent
fi

echo
bold "  ✅  onboarding complete"
dim "  next: open https://q7haa32f.insforge.site — your action should be visible"
dim "  run 'bash scripts/doctor.sh' any time to check health"
dim "  run Gmail later:  .venv/bin/python scripts/onboard.py  (one time)"
echo
