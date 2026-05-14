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


class IngestValidationError(ValueError):
    """Raised when an input row cannot safely become PrivateContext."""


def _required_string(row: dict, field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise IngestValidationError(f"field {field!r} must be a non-empty string")
    return value


def _parse(row: dict) -> PrivateContext:
    sender = row.get("from") or row.get("from_email")
    if not isinstance(sender, str) or not sender.strip():
        raise IngestValidationError(
            "field 'from' or 'from_email' must be a non-empty string"
        )
    participants = row.get("participants", [])
    if not isinstance(participants, list) or not all(
        isinstance(participant, str) for participant in participants
    ):
        raise IngestValidationError("field 'participants' must be a list of strings")
    try:
        last_message_at = datetime.fromisoformat(
            _required_string(row, "last_message_at").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise IngestValidationError(
            "field 'last_message_at' must be an ISO-8601 datetime"
        ) from exc

    return PrivateContext(
        thread_id=_required_string(row, "thread_id"),
        subject=_required_string(row, "subject"),
        from_email=sender,
        from_name=row.get("from_name", ""),
        body=row.get("body", ""),
        participants=participants,
        last_message_at=last_message_at,
    )


def main(path: str) -> int:
    p = Path(path)
    if not p.exists():
        print(f"[ingest] no such file: {path}", file=sys.stderr)
        return 1
    try:
        rows = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        print(f"[ingest] invalid JSON: {exc.msg}", file=sys.stderr)
        return 2
    if not isinstance(rows, list):
        print("[ingest] expected a JSON array of thread records", file=sys.stderr)
        return 2
    contexts: list[PrivateContext] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            print(
                f"[ingest] row {index} must be a thread record object",
                file=sys.stderr,
            )
            return 2
        try:
            ctx = _parse(row)
        except IngestValidationError as exc:
            print(f"[ingest] row {index}: {exc}", file=sys.stderr)
            return 2
        contexts.append(ctx)
    for ctx in contexts:
        private_store.save_thread(ctx)
        print(f"[private] ingested {ctx.thread_id} ({ctx.content_hash()})")
    print(f"[private] total {len(contexts)} threads in private:thread:*")
    print("[ingest] source stays local — no data crossed the boundary")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: ingest_json.py <path-to-threads.json>", file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
