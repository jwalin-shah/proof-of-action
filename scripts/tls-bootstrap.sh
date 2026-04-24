#!/usr/bin/env bash
# Generate a self-signed CA + Redis server cert + agent client cert for local
# mTLS. Demo-grade: everything lands in ./private/tls/ (gitignored).
#
# Layout:
#   private/tls/ca.crt            — root CA (pin this)
#   private/tls/ca.key            — CA private key (keep local)
#   private/tls/redis.{crt,key}   — server leaf, SAN: localhost + 127.0.0.1
#   private/tls/agent.{crt,key}   — client leaf for the private worker
#
# For production (Akash / hosted Redis) replace with a real internal PKI.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TLS_DIR="$ROOT/private/tls"
DAYS="${POA_TLS_DAYS:-825}"

mkdir -p "$TLS_DIR"
chmod 700 "$TLS_DIR"
cd "$TLS_DIR"

gen_key() { openssl genrsa -out "$1" 4096 2>/dev/null; chmod 600 "$1"; }

if [[ ! -f ca.crt ]]; then
  gen_key ca.key
  openssl req -x509 -new -nodes -key ca.key -sha256 -days "$DAYS" \
    -subj "/CN=proof-of-action local CA" -out ca.crt 2>/dev/null
  echo "✓ CA issued: $TLS_DIR/ca.crt"
fi

issue_leaf() {
  local name="$1" san="$2"
  [[ -f "${name}.crt" ]] && return
  gen_key "${name}.key"
  openssl req -new -key "${name}.key" -subj "/CN=${name}" -out "${name}.csr" 2>/dev/null
  cat > "${name}.ext" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth,clientAuth
subjectAltName=${san}
EOF
  openssl x509 -req -in "${name}.csr" -CA ca.crt -CAkey ca.key -CAcreateserial \
    -out "${name}.crt" -days "$DAYS" -sha256 -extfile "${name}.ext" 2>/dev/null
  rm -f "${name}.csr" "${name}.ext"
  echo "✓ ${name} cert issued"
}

issue_leaf redis "DNS:localhost,IP:127.0.0.1"
issue_leaf agent "DNS:proof-of-action.agent"

echo
echo "Next: start Redis with TLS:"
echo "  redis-server deploy/redis-tls.conf"
echo
echo "Then enable TLS in the Python client:"
echo "  export POA_REDIS_TLS=on"
