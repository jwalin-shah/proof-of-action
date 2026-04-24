#!/usr/bin/env bash
# Generate a 32-byte master key for the AES-GCM private envelope.
# Phase G7: write to .env.local as hex. Phase H6 swaps this for macOS
# Keychain.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${POA_ENV_FILE:-$ROOT/.env.local}"

if grep -q '^POA_MASTER_KEY=' "$ENV_FILE" 2>/dev/null; then
  echo "POA_MASTER_KEY already present in $ENV_FILE — not overwriting."
  echo "Delete the line first if you really want to rotate."
  exit 0
fi

HEX=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
printf "\nPOA_MASTER_KEY=%s\n" "$HEX" >> "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo "✓ 32-byte master key appended to $ENV_FILE"
echo "  Load with: set -a; source $ENV_FILE; set +a"
