"""iMessage source adapter. Lives on the private plane — never crosses the boundary.

Reads ``~/Library/Messages/chat.db`` (Apple's SQLite store) in read-only mode,
groups recent messages by chat, and emits one PrivateContext per chat where
the last message is NOT from the operator (i.e. threads the operator likely
owes a reply on).

Prereqs:
  * macOS host
  * Full Disk Access granted to the terminal / Python binary:
      System Settings → Privacy & Security → Full Disk Access
  * POA_SOURCE=imessage in .env.local

Everything stays local: there is no network call at any point.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from proof_of_action.boundary import PrivateContext

DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"

# Apple's "Cocoa epoch": nanoseconds since 2001-01-01. Convert to UTC unix.
COCOA_EPOCH_OFFSET = 978307200


class IMessageUnavailable(RuntimeError):
    """Raised when chat.db is missing or Full Disk Access is not granted."""


def _open_readonly() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise IMessageUnavailable(
            f"{DB_PATH} not found — iMessage adapter only works on macOS"
        )
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)
    except sqlite3.OperationalError as exc:
        raise IMessageUnavailable(
            f"Cannot open {DB_PATH} read-only: {exc}. Grant Full Disk Access to "
            f"your terminal in System Settings → Privacy & Security."
        ) from exc
    # Verify FDA actually works — an unauth'd connection can open but errors on read.
    try:
        conn.execute("SELECT COUNT(*) FROM message LIMIT 1").fetchone()
    except sqlite3.OperationalError as exc:
        conn.close()
        raise IMessageUnavailable(
            f"chat.db opened but read failed: {exc}. Full Disk Access needs "
            f"to cover the process running Python (usually your terminal)."
        ) from exc
    conn.row_factory = sqlite3.Row
    return conn


def _apple_seconds_to_dt(apple_ns: int) -> datetime:
    """chat.db stores `date` as nanoseconds since 2001-01-01 UTC."""
    unix = (apple_ns // 1_000_000_000) + COCOA_EPOCH_OFFSET
    return datetime.fromtimestamp(unix, tz=timezone.utc)


def fetch_threads(
    max_threads: int = 20,
    lookback_days: int = 90,
    min_messages: int = 3,
) -> list[PrivateContext]:
    """Return recent iMessage chats where the operator likely owes a reply.

    Filters: only chats with >= `min_messages` total, last message within
    `lookback_days`, and most-recent message NOT from the operator.
    """
    conn = _open_readonly()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        cutoff_apple_ns = int((cutoff.timestamp() - COCOA_EPOCH_OFFSET) * 1_000_000_000)

        # Pull recent messages with chat + handle joined in one pass.
        rows = conn.execute(
            """
            SELECT
              m.rowid          AS msg_rowid,
              cmj.chat_id      AS chat_id,
              m.text           AS text,
              m.is_from_me     AS is_from_me,
              m.date           AS apple_ns,
              h.id             AS handle,
              c.guid           AS chat_guid,
              c.display_name   AS chat_display_name
            FROM message m
              JOIN chat_message_join cmj ON cmj.message_id = m.rowid
              JOIN chat c                ON c.rowid = cmj.chat_id
              LEFT JOIN handle h         ON h.rowid = m.handle_id
            WHERE m.text IS NOT NULL
              AND m.date > ?
            ORDER BY m.rowid ASC
            """,
            (cutoff_apple_ns,),
        ).fetchall()
    finally:
        conn.close()

    # Group by chat_id.
    chats: dict[int, dict] = {}
    for r in rows:
        cid = r["chat_id"]
        entry = chats.setdefault(
            cid,
            {
                "guid": r["chat_guid"] or f"chat_{cid}",
                "display_name": r["chat_display_name"] or "",
                "handles": set(),
                "messages": [],  # ordered oldest → newest
            },
        )
        if r["handle"]:
            entry["handles"].add(r["handle"])
        entry["messages"].append(
            {
                "from": "me" if r["is_from_me"] else (r["handle"] or "unknown"),
                "text": r["text"],
                "at": _apple_seconds_to_dt(r["apple_ns"]),
            }
        )

    contexts: list[PrivateContext] = []
    for cid, data in chats.items():
        msgs = data["messages"]
        if len(msgs) < min_messages:
            continue
        last = msgs[-1]
        # Skip chats where we sent the last message (nothing to reply to).
        if last["from"] == "me":
            continue

        # Pull the last ~6 messages into a concatenated body — enough signal
        # for the classifier / drafter, not so much that prompts balloon.
        recent = msgs[-6:]
        body = "\n".join(
            f"{m['from']}: {m['text']}" for m in recent if m.get("text")
        )

        sender = last["from"]
        participants = sorted(data["handles"]) or [sender]
        subject = (
            data["display_name"]
            or (f"iMessage with {sender}" if len(participants) == 1 else "iMessage group")
        )

        contexts.append(
            PrivateContext(
                thread_id=f"imsg:{data['guid']}",
                subject=subject,
                from_email=sender,          # handle = phone or email
                from_name=sender,           # Contacts resolution is future work
                body=body,
                participants=participants,
                last_message_at=last["at"],
            )
        )

    # Most-recently-active chats first; cap to max_threads.
    contexts.sort(key=lambda c: c.last_message_at, reverse=True)
    return contexts[:max_threads]


def is_available() -> bool:
    """Quick probe for doctor.sh — does chat.db exist and are we allowed in."""
    try:
        conn = _open_readonly()
        conn.close()
        return True
    except IMessageUnavailable:
        return False
