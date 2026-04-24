"""Gmail source adapter. Lives on the private plane — never crosses the boundary.

Loads the OAuth token from ~/.config/proof-of-action/gmail-token.json (produced
by scripts/onboard.py), fetches the most recent threads, and converts each to a
PrivateContext for the agent. The token and raw message contents stay local.
"""
from __future__ import annotations

import base64
import email
import re
from datetime import datetime, timezone
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from proof_of_action.boundary import PrivateContext

TOKEN_FILE = Path.home() / ".config" / "proof-of-action" / "gmail-token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailOnboardRequired(RuntimeError):
    pass


def _svc():
    if not TOKEN_FILE.exists():
        raise GmailOnboardRequired(
            f"No Gmail token at {TOKEN_FILE}. Run: python scripts/onboard.py"
        )
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _body_from_payload(payload: dict) -> str:
    """Flatten multipart payload to a plaintext body (best effort)."""
    if not payload:
        return ""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {}) or {}
    data = body.get("data")
    if data and mime.startswith("text/"):
        raw = base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")
        if mime == "text/html":
            raw = re.sub(r"<[^>]+>", " ", raw)
            raw = re.sub(r"\s+", " ", raw).strip()
        return raw
    parts = payload.get("parts") or []
    for part in parts:
        text = _body_from_payload(part)
        if text:
            return text
    return ""


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def fetch_threads(max_threads: int = 5, query: str = "in:inbox") -> list[PrivateContext]:
    svc = _svc()
    resp = svc.users().threads().list(userId="me", q=query, maxResults=max_threads).execute()
    thread_ids = [t["id"] for t in resp.get("threads", [])]

    contexts: list[PrivateContext] = []
    for tid in thread_ids:
        thread = svc.users().threads().get(userId="me", id=tid, format="full").execute()
        messages = thread.get("messages", [])
        if not messages:
            continue

        first = messages[0]
        last = messages[-1]
        headers = first.get("payload", {}).get("headers", [])
        subject = _header(headers, "Subject") or "(no subject)"
        from_raw = _header(headers, "From")
        from_name, from_email = parseaddr(from_raw)
        if not from_name:
            from_name = from_email.split("@")[0] if from_email else "Unknown"

        participants: set[str] = set()
        for msg in messages:
            h = msg.get("payload", {}).get("headers", [])
            for field in ("From", "To", "Cc"):
                raw = _header(h, field)
                for _, addr in getaddresses([raw]):
                    if addr:
                        participants.add(addr)

        last_headers = last.get("payload", {}).get("headers", [])
        date_raw = _header(last_headers, "Date")
        try:
            last_at = parsedate_to_datetime(date_raw) if date_raw else datetime.now(timezone.utc)
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            last_at = datetime.now(timezone.utc)

        body = _body_from_payload(last.get("payload", {}))[:4000]

        contexts.append(
            PrivateContext(
                thread_id=f"gmail:{tid}",
                subject=subject,
                from_email=from_email or "unknown@unknown",
                from_name=from_name,
                body=body,
                participants=sorted(participants),
                last_message_at=last_at,
            )
        )

    return contexts
