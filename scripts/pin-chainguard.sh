#!/usr/bin/env bash
# Refresh the Chainguard base-image digests pinned in Dockerfile + .chainguard-digest.
# Uses only curl — no docker / crane / skopeo needed.
#
# Run this when you want to pick up upstream CVE fixes. The whole supply
# chain (Dockerfile → CI scan → cited.md Provenance block) reads from the
# same two sha256 values, so one refresh propagates everywhere.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fetch_digest() {
  local tag="$1"
  local token
  token=$(curl -s "https://cgr.dev/token?service=cgr.dev&scope=repository:chainguard/python:pull" \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
  curl -sI \
    -H "Authorization: Bearer $token" \
    -H "Accept: application/vnd.oci.image.index.v1+json" \
    "https://cgr.dev/v2/chainguard/python/manifests/${tag}" \
    | awk -F': ' 'tolower($1)=="docker-content-digest"{sub(/\r$/,"",$2);print $2}'
}

RUNTIME_DIGEST=$(fetch_digest latest)
BUILDER_DIGEST=$(fetch_digest latest-dev)

if [[ -z "$RUNTIME_DIGEST" || -z "$BUILDER_DIGEST" ]]; then
  echo "✗ failed to fetch a digest — check network and Chainguard registry status"
  exit 1
fi

echo "  latest     → $RUNTIME_DIGEST"
echo "  latest-dev → $BUILDER_DIGEST"

# Update Dockerfile in place (the @sha256:... suffix after each base tag).
sed -i.bak -E \
  -e "s|(cgr\.dev/chainguard/python:latest-dev)@sha256:[0-9a-f]+|\1@${BUILDER_DIGEST}|" \
  -e "s|(cgr\.dev/chainguard/python:latest)@sha256:[0-9a-f]+|\1@${RUNTIME_DIGEST}|" \
  Dockerfile
rm -f Dockerfile.bak

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > .chainguard-digest <<EOF
# Proof-of-Action — Chainguard base image pins (Phase G2).
# Refreshed by scripts/pin-chainguard.sh. Read by the provenance block in
# cited.md so judges can verify the exact bytes we built against.
#
# Format: <tag> <sha256 digest>  (last-refreshed ISO-8601)
latest     ${RUNTIME_DIGEST}
latest-dev ${BUILDER_DIGEST}
last-refreshed ${NOW}
EOF

echo "✓ Dockerfile + .chainguard-digest updated"
