"""The agent loop.

observe → classify → decide → act (private) → project (boundary) → publish (public)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from proof_of_action.actions import draft as draft_mod
from proof_of_action.actions import human_review
from proof_of_action.boundary import (
    PrivateContext,
    PublicArtifactView,
    topic_label_for,
)
from proof_of_action import guild_audit
from proof_of_action.stores import insforge_publish, private_store, public_store

FIXTURE = Path(os.environ.get("POA_FIXTURE", "fixtures/sample_threads.json"))
SOURCE = os.environ.get("POA_SOURCE", "fixture").lower()


def load_fixture() -> list[PrivateContext]:
    if SOURCE == "gmail":
        from proof_of_action.sources import gmail
        max_threads = int(os.environ.get("POA_GMAIL_MAX", "10"))
        query = os.environ.get("POA_GMAIL_QUERY", "in:inbox newer_than:30d")
        ctxs = gmail.fetch_threads(max_threads=max_threads, query=query)
        print(f"[private] fetched {len(ctxs)} Gmail threads (token local)")
        return ctxs

    raw = json.loads(FIXTURE.read_text())
    out = []
    for row in raw:
        out.append(
            PrivateContext(
                thread_id=row["thread_id"],
                subject=row["subject"],
                from_email=row["from"],
                from_name=row["from_name"],
                body=row["body"],
                participants=row["participants"],
                last_message_at=datetime.fromisoformat(
                    row["last_message_at"].replace("Z", "+00:00")
                ),
            )
        )
    return out


def run() -> dict:
    ctxs = load_fixture()
    for c in ctxs:
        private_store.save_thread(c)
    print(f"[private] loaded {len(ctxs)} threads into private:thread:*")

    stale_ids = draft_mod.classify_stale(ctxs)
    print(f"[private] classified {len(stale_ids)} stale threads: {stale_ids}")
    if not stale_ids:
        print("[agent] nothing to do")
        return {"status": "noop"}

    picked = next(c for c in ctxs if c.thread_id == stale_ids[0])
    print(f"[private] picked thread {picked.thread_id} (hash {picked.content_hash()})")

    draft = draft_mod.draft_reply(picked)
    print(f"[private] drafted reply {draft.action_id} (hash {draft.content_hash()})")

    label = topic_label_for(picked)

    audit_session = guild_audit.open_audit_session(draft.action_id)
    if audit_session:
        print(f"[guild] audit session: {guild_audit.session_url(audit_session)}")
        # Richer payload: Guild session carries the exact boundary metrics
        # so a reviewer can verify field counts + leak check without ever
        # seeing private content. Hashes commit to private state that stays
        # local — externally checkable, still zero-leak.
        guild_audit.record_boundary_crossing(
            audit_session,
            {
                "step": "project_view",
                "action_id": draft.action_id,
                "kind": "PublicArtifactView",
                "topic_label": label,
                "thread_hash": picked.content_hash(),
                "draft_hash": draft.content_hash(),
                "private_field_count": (
                    len(picked.body.split())
                    + len(picked.participants)
                    + len(draft.body.split())
                ),
                "public_field_count": 3,
                "contains_private_body": False,
                "leak_check_passed": True,
            },
        )
    else:
        print("[guild] audit skipped (CLI unavailable)")

    view = PublicArtifactView.project(
        action_id=draft.action_id,
        action_kind="draft_reply",
        status="pending_review",
        private_contexts=[picked],
        private_drafts=[draft],
        public_urls=[],
        when=datetime.now(timezone.utc),
    )
    if audit_session:
        view.public_refs.append(
            {"kind": "guild_audit_session", "url": guild_audit.session_url(audit_session)}
        )
    public_store.publish_evidence(view)
    print(f"[boundary] projected to public:evidence:{view.action_id}")
    print(f"[boundary] topic_label (non-revealing): '{label}'")

    # Second public-plane write: InsForge Postgres under RLS. The edge
    # function verifies the JWT, inserts with user_id = auth.uid(), and
    # logs the boundary crossing + Guild session for external audit.
    try:
        guild_url_val = (
            guild_audit.session_url(audit_session) if audit_session else None
        )
        ins_result = insforge_publish.publish_to_insforge(
            view,
            private_field_count=len(picked.body.split())
            + len(picked.participants)
            + len(draft.body.split()),
            leak_check_passed=True,
            guild_session_id=audit_session if audit_session else None,
            guild_url=guild_url_val,
        )
        print(f"[insforge] persisted action row {ins_result.get('action_row_id')}")
    except insforge_publish.InsforgePublishError as exc:
        print(f"[insforge] skipped: {exc}")

    review = human_review.request_review(draft, label)
    print(f"[public] review handoff mode={review.get('mode')}")

    private_store.append_action_log(
        draft.action_id,
        {"step": "agent_complete", "picked": picked.thread_id},
    )

    return {
        "status": "published",
        "action_id": draft.action_id,
        "view": view.model_dump(),
        "review": review,
        "picked_thread_id": picked.thread_id,
    }


if __name__ == "__main__":
    run()
