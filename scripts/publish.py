"""Generate cited.md from public:evidence:* and (optionally) host on Insforge.

Privacy properties:
  * Day-granularity timestamps (no seconds → weakens timing correlation)
  * Counts over enumeration (aggregate where possible)
  * Private refs appear only as sha256 hashes
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

from proof_of_action.stores import public_store

OUT = Path("artifacts/cited.md")


def _load_env_local() -> None:
    env_file = Path(".env.local")
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env_local()
INSFORGE_URL = os.environ.get("INSFORGE_PROJECT_URL")
INSFORGE_KEY = os.environ.get("INSFORGE_ACCESS_KEY")
INSFORGE_TABLE = os.environ.get("INSFORGE_TABLE", "proof_actions")
INSFORGE_BUCKET = os.environ.get("INSFORGE_BUCKET", "proof-artifacts")
INSFORGE_DASHBOARD = os.environ.get("INSFORGE_DASHBOARD", "")


def build_cited_md() -> str:
    views = public_store.all_evidence()
    kinds = Counter(v.action_kind for v in views)
    statuses = Counter(v.status for v in views)
    days = sorted({v.day for v in views})

    lines: list[str] = []
    lines.append("# Proof-of-Action — Public Citation")
    lines.append("")
    lines.append("> An agent took action on private context. This artifact is the")
    lines.append("> public, redacted, verifiable record. Private content stays local.")
    lines.append("")
    lines.append("## What this artifact proves")
    lines.append("")
    lines.append("**Defended (by our code):** No private field value appears in this")
    lines.append("document. Refs are peppered sha256 commitments, not reversible.")
    lines.append("Downstream services (Guild, Insforge) only see typed projections.")
    lines.append("")
    lines.append("**Trusted (inside the private TCB):** Anthropic API (no ZDR by")
    lines.append("default — documented), local inbox ingest server, operator machine.")
    lines.append("")
    lines.append("**Out of scope (would be overclaim):** cryptographic privacy,")
    lines.append("oblivious execution, side-channel resistance beyond day-granularity batching.")
    lines.append("")
    lines.append("## Activity summary")
    lines.append("")
    lines.append(f"- Actions: **{len(views)}**")
    lines.append(f"- Days active: {', '.join(days) if days else '—'}")
    lines.append(f"- By kind: {dict(kinds)}")
    lines.append(f"- By status: {dict(statuses)}")
    lines.append("")
    lines.append("## Actions (hashed)")
    lines.append("")
    for v in views:
        lines.append(f"### `{v.action_id}` — {v.action_kind} — {v.day}")
        lines.append("")
        lines.append(f"- Status: `{v.status}`")
        lines.append("- Private evidence referenced:")
        for ref in v.private_refs:
            lines.append(f"  - `{ref['kind']}` → `{ref['hash']}`")
        if v.public_refs:
            lines.append("- Public evidence:")
            for ref in v.public_refs:
                lines.append(f"  - {ref.get('url', '')}")
        lines.append("")
    lines.append("## Verifiability")
    lines.append("")
    lines.append("Each sha256 hash commits to a private item held only on the")
    lines.append("operator's machine. A reviewer can request a local verification")
    lines.append("(`scripts/verify_hash.py <hash>`) to confirm an item exists")
    lines.append("without the item ever being published.")
    lines.append("")
    lines.append("## Infrastructure")
    lines.append("")
    lines.append("- **Redis** (two-user ACL): enforces the private/public keyspace split at the infra layer.")
    lines.append("- **Chainguard** (container): minimal, CVE-hardened base image for the private zone.")
    lines.append("- **Guild.ai** (orchestration): audit trail of boundary crossings + human review workflow.")
    lines.append("- **Insforge** (hosting): serves this public artifact; never sees private context.")
    lines.append("- **Akash** (decentralized compute): public research workers; designed for, deploy manifest in `deploy/`.")
    lines.append("")
    lines.append(
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')} — "
        "day-granularity is intentional._"
    )
    return "\n".join(lines)


def upload_to_insforge(md: str, views: list) -> dict:
    """POST each action row + attach the cited.md to every row (small demo)."""
    if not (INSFORGE_URL and INSFORGE_KEY):
        return {"mode": "local_only"}
    if not views:
        return {"mode": "insforge_skipped", "reason": "no views"}
    rows = []
    for v in views:
        rows.append(
            {
                "action_id": v.action_id,
                "action_kind": v.action_kind,
                "day": v.day,
                "status": v.status,
                "private_refs": v.private_refs,
                "public_refs": v.public_refs,
                "cited_md": md,
            }
        )
    try:
        r = httpx.post(
            f"{INSFORGE_URL}/api/database/records/{INSFORGE_TABLE}",
            json=rows,
            headers={
                "Authorization": f"Bearer {INSFORGE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            timeout=15,
        )
        return {
            "mode": "insforge",
            "status": r.status_code,
            "rows_sent": len(rows),
            "dashboard": INSFORGE_DASHBOARD,
            "body": r.text[:300],
        }
    except Exception as e:
        return {"mode": "insforge_error", "error": str(e)[:200]}


def upload_cited_to_bucket(md_path: Path) -> dict:
    """Upload cited.md to the public Insforge Storage bucket → live CDN URL.

    Deletes first so the URL stays stable (cited.md, not 'cited (1).md').
    """
    if not (INSFORGE_URL and INSFORGE_KEY):
        return {"mode": "local_only"}
    base = f"{INSFORGE_URL}/api/storage/buckets/{INSFORGE_BUCKET}/objects/cited.md"
    headers = {"x-api-key": INSFORGE_KEY}
    try:
        httpx.delete(base, headers=headers, timeout=10)
        with open(md_path, "rb") as fh:
            r = httpx.put(
                base,
                headers=headers,
                files={"file": ("cited.md", fh, "text/markdown")},
                timeout=15,
            )
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "mode": "insforge_storage",
            "status": r.status_code,
            "public_url": body.get("url") or base,
            "size": body.get("size"),
        }
    except Exception as e:
        return {"mode": "storage_error", "error": str(e)[:200]}


def main() -> None:
    md = build_cited_md()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(md)
    print(f"[public] wrote {OUT} ({len(md)} chars)")
    views = public_store.all_evidence()
    up = upload_to_insforge(md, views)
    print(f"[public] insforge db: {up.get('mode')} status={up.get('status')} rows={up.get('rows_sent')}")
    bucket = upload_cited_to_bucket(OUT)
    print(f"[public] insforge storage: {bucket.get('mode')} status={bucket.get('status')}")
    if bucket.get("public_url"):
        print(f"[public] LIVE URL: {bucket['public_url']}")


if __name__ == "__main__":
    main()
