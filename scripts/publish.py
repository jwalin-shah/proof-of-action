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


def build_dashboard_html(views: list, cited_url: str) -> str:
    """Static-render dashboard. No API key exposed client-side.

    Shows each action with hashes, Guild audit session link (if present),
    status, and a link to the raw cited.md artifact.
    """
    rows_html = []
    for v in views:
        refs_rows = "\n".join(
            f'<tr><td><code>{r.get("kind","")}</code></td>'
            f'<td class="hash">{r.get("hash","")}</td></tr>'
            for r in v.private_refs
        )
        guild_links = [r for r in v.public_refs if r.get("kind") == "guild_audit_session"]
        guild_html = (
            "<div class='guild-link'>🔍 Guild audit: "
            f"<a href='{guild_links[0]['url']}' target='_blank'>"
            f"{guild_links[0]['url']}</a></div>"
            if guild_links else ""
        )
        rows_html.append(f"""
<article class="action">
  <header>
    <code class="action-id">{v.action_id}</code>
    <span class="kind">{v.action_kind}</span>
    <span class="day">{v.day}</span>
    <span class="status status-{v.status}">{v.status}</span>
  </header>
  <table class="refs">
    <thead><tr><th>kind</th><th>sha256 (peppered)</th></tr></thead>
    <tbody>{refs_rows}</tbody>
  </table>
  {guild_html}
</article>
""")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Proof-of-Action — Public Dashboard</title>
<style>
  :root {{ color-scheme: dark light; --accent:#5eead4; --bg:#0b0f14; --card:#141b24; --fg:#e6edf3; --muted:#8b949e; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
         background:var(--bg); color:var(--fg); padding:2rem; max-width:860px; margin:auto; line-height:1.6; }}
  h1 {{ font-size:1.8rem; margin-bottom:0.2rem; }}
  .tagline {{ color:var(--muted); margin-top:0; }}
  .stack {{ display:flex; flex-wrap:wrap; gap:0.5rem; margin:1rem 0 2rem; }}
  .pill {{ background:var(--card); padding:0.3rem 0.7rem; border-radius:999px; font-size:0.85rem; color:var(--muted); border:1px solid #222; }}
  .pill b {{ color:var(--accent); }}
  article.action {{ background:var(--card); border-radius:12px; padding:1.2rem; margin-bottom:1rem; border:1px solid #1a2333; }}
  article.action header {{ display:flex; gap:1rem; align-items:baseline; flex-wrap:wrap; }}
  .action-id {{ background:#000; padding:2px 6px; border-radius:4px; color:var(--accent); font-size:0.9rem; }}
  .kind {{ color:var(--accent); font-weight:500; }}
  .day {{ color:var(--muted); font-size:0.85rem; }}
  .status {{ margin-left:auto; padding:2px 8px; border-radius:4px; font-size:0.75rem; background:#222; }}
  .status-pending_review {{ background:#3b2e00; color:#ffd872; }}
  table.refs {{ width:100%; border-collapse:collapse; margin-top:0.8rem; font-size:0.85rem; }}
  table.refs th {{ text-align:left; color:var(--muted); font-weight:500; padding:0.3rem 0.5rem; border-bottom:1px solid #1a2333; }}
  table.refs td {{ padding:0.4rem 0.5rem; }}
  td.hash {{ font-family:"SF Mono",Menlo,Consolas,monospace; color:var(--muted); font-size:0.78rem; word-break:break-all; }}
  .guild-link {{ margin-top:0.8rem; padding:0.6rem 0.8rem; background:#0a2e2a; border-left:3px solid var(--accent); border-radius:4px; font-size:0.85rem; }}
  .guild-link a {{ color:var(--accent); word-break:break-all; }}
  footer {{ color:var(--muted); font-size:0.82rem; margin-top:2rem; padding-top:1rem; border-top:1px solid #1a2333; }}
  a.cta {{ display:inline-block; background:var(--accent); color:#000; padding:0.5rem 1rem; border-radius:6px; font-weight:600; text-decoration:none; margin-top:0.5rem; }}
</style>
</head>
<body>
  <h1>Proof-of-Action</h1>
  <p class="tagline">Self-hostable OpenHuman — a personal AI agent that acts on private context and publishes a redacted, externally-verifiable public record of what it did.</p>

  <div class="stack">
    <span class="pill">🔒 <b>Private zone</b> local only</span>
    <span class="pill">🔥 <b>Redis ACL</b> NOPERM verified</span>
    <span class="pill">📦 <b>Chainguard</b> container</span>
    <span class="pill">🌐 <b>Insforge</b> Postgres + Storage</span>
    <span class="pill">🔍 <b>Guild</b> audit sessions</span>
    <span class="pill">☁️ <b>Akash</b> deploy manifest</span>
  </div>

  <a class="cta" href="{cited_url}" target="_blank">📄 Read the full cited.md →</a>

  <h2 style="margin-top:2rem">Actions</h2>
  {''.join(rows_html) if rows_html else '<p style="color:var(--muted)">No actions yet. Run <code>python scripts/demo.py</code>.</p>'}

  <footer>
    Built at <b>Ship to Prod</b>, AWS Builder Loft SF, 2026-04-24.
    Private reasoning never reaches this page. Only typed projections and peppered sha256 commitments.
    Hashes here are non-reversible without the operator's <code>HASH_PEPPER</code>.
  </footer>
</body>
</html>"""


def upload_dashboard(html: str) -> dict:
    if not (INSFORGE_URL and INSFORGE_KEY):
        return {"mode": "local_only"}
    base = f"{INSFORGE_URL}/api/storage/buckets/{INSFORGE_BUCKET}/objects/index.html"
    headers = {"x-api-key": INSFORGE_KEY}
    try:
        httpx.delete(base, headers=headers, timeout=10)
        import io
        r = httpx.put(
            base,
            headers=headers,
            files={"file": ("index.html", io.BytesIO(html.encode()), "text/html")},
            timeout=15,
        )
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return {"mode": "dashboard", "status": r.status_code, "public_url": body.get("url") or base}
    except Exception as e:
        return {"mode": "dashboard_error", "error": str(e)[:200]}


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
    cited_url = bucket.get("public_url") or ""
    if cited_url:
        print(f"[public] cited.md URL: {cited_url}")

    html = build_dashboard_html(views, cited_url)
    dash = upload_dashboard(html)
    print(f"[public] dashboard: {dash.get('mode')} status={dash.get('status')}")
    if dash.get("public_url"):
        print(f"[public] DASHBOARD URL: {dash['public_url']}")


if __name__ == "__main__":
    main()
