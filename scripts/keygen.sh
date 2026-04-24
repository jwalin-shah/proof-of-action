#!/usr/bin/env bash
# Generate or migrate the 32-byte master key for the AES-GCM private envelope.
#
# Modes:
#   ./scripts/keygen.sh             — append POA_MASTER_KEY= to .env.local (dev)
#   ./scripts/keygen.sh --keychain  — store in macOS Keychain (H6, recommended)
#   ./scripts/keygen.sh --migrate   — copy existing .env.local key INTO Keychain
#                                     then strip it from .env.local

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${POA_ENV_FILE:-$ROOT/.env.local}"
SERVICE="proof-of-action"
ACCOUNT="master-key"

mode="${1:-env}"

keychain_store() {
  local hex="$1"
  if ! command -v security >/dev/null 2>&1; then
    echo "✗ 'security' (Keychain) not available — are you on macOS?"
    exit 1
  fi
  security delete-generic-password -s "$SERVICE" -a "$ACCOUNT" >/dev/null 2>&1 || true
  security add-generic-password -s "$SERVICE" -a "$ACCOUNT" -w "$hex" -U
  echo "✓ master key stored in Keychain (service=$SERVICE account=$ACCOUNT)"
  echo "  Read with: security find-generic-password -s $SERVICE -a $ACCOUNT -w"
}

case "$mode" in
  --keychain)
    HEX=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    keychain_store "$HEX"
    echo "  POA_MASTER_KEY in env is no longer required — crypto.py prefers Keychain."
    ;;
  --migrate)
    if ! grep -q '^POA_MASTER_KEY=' "$ENV_FILE" 2>/dev/null; then
      echo "✗ no POA_MASTER_KEY in $ENV_FILE to migrate"
      exit 1
    fi
    HEX=$(grep '^POA_MASTER_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2-)
    keychain_store "$HEX"
    # Strip the line so future loads read from Keychain only.
    sed -i.bak '/^POA_MASTER_KEY=/d' "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    echo "✓ POA_MASTER_KEY removed from $ENV_FILE — Keychain is the source of truth now."
    ;;
  --help|-h)
    grep -E '^#' "$0" | head -10 | sed 's/^# \?//'
    ;;
  *)
    # Default: env-file mode (back-compat with prior behavior).
    if grep -q '^POA_MASTER_KEY=' "$ENV_FILE" 2>/dev/null; then
      echo "POA_MASTER_KEY already present in $ENV_FILE — not overwriting."
      echo "  Rotate: delete the line first, or use --keychain to move it."
      exit 0
    fi
    HEX=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    printf "\nPOA_MASTER_KEY=%s\n" "$HEX" >> "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "✓ 32-byte master key appended to $ENV_FILE"
    echo "  Load with: set -a; source $ENV_FILE; set +a"
    echo "  Upgrade: ./scripts/keygen.sh --migrate  (move into Keychain)"
    ;;
esac
