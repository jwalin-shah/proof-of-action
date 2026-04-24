"""Guild.ai audit wiring.

Each demo run opens a Guild session. Every boundary crossing is sent to the
session as a message, producing an independent, immutable audit trail on
Guild — our "don't trust our app logic, trust Guild" layer.

Falls back to no-op if guild CLI is missing or auth is gone. Never blocks
or raises.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Optional

AGENT_IDENT = "jwalinshah13/hello-agent"


def _run(cmd: list[str], timeout: int = 10) -> Optional[dict]:
    if not shutil.which("guild"):
        return None
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return None
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return {"_raw": r.stdout}
    except Exception:
        return None


def open_audit_session(action_id: str) -> Optional[str]:
    prompt = f"audit_session for {action_id} at {datetime.now(timezone.utc).isoformat()}"
    res = _run(
        [
            "guild",
            "--json",
            "session",
            "create",
            "--type",
            "chat",
            "--agent",
            AGENT_IDENT,
            "--prompt",
            prompt,
        ],
        timeout=20,
    )
    if not res:
        return None
    return res.get("id")


def record_boundary_crossing(session_id: str, event: dict) -> bool:
    msg = "boundary_crossing " + " ".join(f"{k}={v}" for k, v in event.items())
    res = _run(["guild", "session", "send", session_id, "--message", msg])
    return res is not None


def session_url(session_id: str) -> str:
    return f"https://app.guild.ai/sessions/{session_id}"
