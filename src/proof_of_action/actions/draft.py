"""Claude-backed draft generation.

Sensitivity-tagged: the prompt carries private content, so the request is
logged as a 'private' boundary crossing to the reasoning TCB (Anthropic).
This is the one cross-zone trust assumption we accept — documented in
cited.md threat model.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from anthropic import Anthropic

from proof_of_action.boundary import (
    PrivateContext,
    PrivateDraft,
    redact_for_llm,
)
from proof_of_action.stores import private_store

MODEL = "claude-sonnet-4-6"


def classify_stale(threads: list[PrivateContext]) -> list[str]:
    """Pick thread_ids the user likely owes a response on.

    Heuristic first so demo works offline; Claude refines if key is set.
    """
    now = datetime.now(timezone.utc)
    stale_candidates = []
    for t in threads:
        age_days = (now - t.last_message_at).days
        if age_days < 14:
            continue
        subj = t.subject.lower()
        if any(w in subj for w in ("invoice", "billing", "receipt", "unsubscribe")):
            continue
        stale_candidates.append((age_days, t.thread_id))
    stale_candidates.sort(reverse=True)
    return [tid for _, tid in stale_candidates]


def draft_reply(ctx: PrivateContext) -> PrivateDraft:
    action_id = "act_" + uuid.uuid4().hex[:8]
    private_store.append_action_log(
        action_id,
        {
            "step": "draft_start",
            "sensitivity": "private",
            "crosses_to": "anthropic_tcb",
            "thread_hash": ctx.content_hash(),
        },
    )

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        body = (
            f"Hi {ctx.from_name.split()[0]},\n\n"
            f"Thanks for your note on '{ctx.subject}'. Apologies for the late "
            f"reply — wanted to circle back now that I've had a chance to review. "
            f"Happy to pick this up again; proposing a call next week.\n\n"
            f"Best,\nJamie"
        )
        model_used = "local_template_fallback"
    else:
        client = Anthropic(api_key=key)
        redacted = redact_for_llm(ctx)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=(
                "You draft short, warm professional replies. "
                "Reply from 'Jamie'. One short paragraph + signoff. "
                "No confidential details. No commitments."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Draft a reply to this stale thread:\n\n"
                        f"Subject: {redacted['subject']}\n"
                        f"Last message: {redacted['last_message_at']}\n"
                        f"Body: {redacted['body']}"
                    ),
                }
            ],
        )
        body = resp.content[0].text
        model_used = MODEL

    draft = PrivateDraft(
        action_id=action_id,
        thread_id=ctx.thread_id,
        body=body,
        model=model_used,
        generated_at=datetime.now(timezone.utc),
    )
    private_store.save_draft(draft)
    private_store.append_action_log(
        action_id,
        {
            "step": "draft_complete",
            "sensitivity": "private",
            "draft_hash": draft.content_hash(),
            "model": model_used,
        },
    )
    return draft
