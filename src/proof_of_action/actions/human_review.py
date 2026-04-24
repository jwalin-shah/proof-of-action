"""Human-review handoff via Guild.ai.

Guild sees only the OpenhumanView / topic_label — never the draft body.
Full audit trail of the boundary crossing is recorded on the private side.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from proof_of_action.boundary import (
    OpenhumanView,
    PrivateDraft,
    VapiView,
    topic_label_for,
)
from proof_of_action.stores import insforge_publish, private_store

GUILD_ENDPOINT = os.environ.get(
    "GUILD_ENDPOINT", "https://api.guild.ai/v1/workflows/runs"
)
GUILD_TOKEN = os.environ.get("GUILD_TOKEN")
FALLBACK_DIR = Path("artifacts/human_review")

# Optional: InsForge email notification on review handoff. Only the
# topic_label + action_id travel — both are already public-plane safe.
REVIEW_NOTIFY_EMAIL = os.environ.get("POA_REVIEW_NOTIFY_EMAIL")


def request_review(draft: PrivateDraft, topic_label: str) -> dict:
    """Trigger a Guild workflow run carrying only the redacted view.

    Records the boundary crossing in the private action log.
    """
    oh_view = OpenhumanView(
        action_id=draft.action_id,
        action_kind="draft_reply",
        status="pending_review",
        public_evidence_refs=[draft.content_hash()],
    )
    vp_view = VapiView.project(draft, topic_label)

    payload = {
        "workflow": "human_review_required",
        "inputs": {
            "action_id": draft.action_id,
            "result": oh_view.model_dump(),
            "notice": vp_view.script,
        },
    }

    private_store.append_action_log(
        draft.action_id,
        {
            "step": "boundary_crossing",
            "sensitivity": "public",
            "target": "guild.ai",
            "view_type": "OpenhumanView",
            "payload_hash_refs": oh_view.public_evidence_refs,
            "contains_private_body": False,
        },
    )

    # Notify the operator via InsForge email. Only topic_label + action_id
    # cross the boundary; both are already public-plane safe.
    if REVIEW_NOTIFY_EMAIL:
        try:
            email_result = insforge_publish.send_review_email(
                REVIEW_NOTIFY_EMAIL, draft.action_id, topic_label
            )
            private_store.append_action_log(
                draft.action_id,
                {
                    "step": "review_email_sent",
                    "sensitivity": "public",
                    "target": "insforge.emails",
                    "status": email_result.get("status"),
                },
            )
        except Exception as e:
            private_store.append_action_log(
                draft.action_id,
                {"step": "review_email_error", "error": str(e)[:200]},
            )

    if GUILD_TOKEN:
        try:
            r = httpx.post(
                GUILD_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {GUILD_TOKEN}"},
                timeout=10,
            )
            return {"mode": "guild", "status": r.status_code, "run": r.json()}
        except Exception as e:
            private_store.append_action_log(
                draft.action_id,
                {"step": "guild_error", "error": str(e)[:200]},
            )

    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    path = FALLBACK_DIR / f"{draft.action_id}.json"
    path.write_text(
        json.dumps(
            {
                **payload,
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "note": "Guild not configured; queued locally for review.",
            },
            indent=2,
        )
    )
    return {"mode": "local_queue", "path": str(path)}
