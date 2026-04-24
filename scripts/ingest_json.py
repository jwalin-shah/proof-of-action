"""Load a JSON dump of thread-shaped records into the private zone.

    $ python scripts/ingest_json.py fixtures/sample_threads.json
    $ python scripts/ingest_json.py ~/exports/my_inbox_dump.json

Accepts records with keys: thread_id, subject, from, from_name, body,
participants, last_message_at. Unknown keys are ignored.

This runs LOCALLY ONLY. It never sends raw content anywhere. The whole
point of the privacy boundary is that ingestion stays on the operator's
machine — Insforge / Guild / cited.md never see raw inbox content.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from proof_of_action.boundary import PrivateContext
from proof_of_action.stores import private_store


def _parse(row: dict) -> PrivateContext:
    return PrivateContext(
        thread_id=row["thread_id"],
        subject=row["subject"],
        from_email=row.get("from") or row.get("from_email", ""),
        from_name=row.get("from_name", ""),
        body=row.get("body", ""),
        participants=row.get("participants", []),
        last_message_at=datetime.fromisoformat(
            row["last_message_at"].replace("Z", "+00:00")
        ),
    )


def main(path: str) -> int:
    p = Path(path)
    if not p.exists():
        print(f"[ingest] no such file: {path}", file=sys.stderr)
        return 1
    rows = json.loads(p.read_text())
    if not isinstance(rows, list):
        print("[ingest] expected a JSON array of thread records", file=sys.stderr)
        return 2
    for row in rows:
        ctx = _parse(row)
        private_store.save_thread(ctx)
        print(f"[private] ingested {ctx.thread_id} ({ctx.content_hash()})")
    print(f"[private] total {len(rows)} threads in private:thread:*")
    print(f"[ingest] source stays local — no data crossed the boundary")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: ingest_json.py <path-to-threads.json>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
