"""The agent loop.

observe → classify → draft → project → audit → publish (typed use-cases)
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path

from proof_of_action.actions import draft as draft_mod
from proof_of_action.actions import human_review
from proof_of_action.boundary import (
    PrivateContext,
    PrivateDraft,
    PublicArtifactView,
    topic_label_for,
)
from proof_of_action import guild_audit
from proof_of_action.boundary_verifier import (
    BoundaryVerification,
    BoundaryVerificationError,
    BoundaryVerifier,
    ProjectionType,
    SharedBoundaryVerifier,
)
from proof_of_action.stores import insforge_publish, private_store, public_store

FIXTURE = Path(os.environ.get("POA_FIXTURE", "fixtures/sample_threads.json"))
SOURCE = os.environ.get("POA_SOURCE", "fixture").lower()


@dataclass(frozen=True)
class ObservedContext:
    threads: list[PrivateContext]
    stale_thread_ids: list[str]


@dataclass(frozen=True)
class DraftedContext:
    picked: PrivateContext
    draft: PrivateDraft
    topic_label: str


def load_fixture() -> list[PrivateContext]:
    if SOURCE == "gmail":
        from proof_of_action.sources import gmail

        max_threads = int(os.environ.get("POA_GMAIL_MAX", "10"))
        query = os.environ.get("POA_GMAIL_QUERY", "in:inbox newer_than:30d")
        ctxs = gmail.fetch_threads(max_threads=max_threads, query=query)
        print(f"[private] fetched {len(ctxs)} Gmail threads (token local)")
        return ctxs

    if SOURCE == "imessage":
        from proof_of_action.sources import imessage

        max_threads = int(os.environ.get("POA_IMSG_MAX", "20"))
        lookback_days = int(os.environ.get("POA_IMSG_LOOKBACK_DAYS", "90"))
        ctxs = imessage.fetch_threads(
            max_threads=max_threads, lookback_days=lookback_days
        )
        print(f"[private] fetched {len(ctxs)} iMessage chats (chat.db read-only)")
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


def run_observe() -> ObservedContext:
    ctxs = load_fixture()
    for c in ctxs:
        private_store.save_thread(c)
    print(f"[private] loaded {len(ctxs)} threads into private:thread:*")

    stale_ids = draft_mod.classify_stale(ctxs)
    print(f"[private] classified {len(stale_ids)} stale threads: {stale_ids}")
    return ObservedContext(threads=ctxs, stale_thread_ids=stale_ids)


def run_draft(observed: ObservedContext) -> DraftedContext:
    if not observed.stale_thread_ids:
        raise ValueError("no stale threads available")
    picked = next(
        c for c in observed.threads if c.thread_id == observed.stale_thread_ids[0]
    )
    print(f"[private] picked thread {picked.thread_id} (hash {picked.content_hash()})")
    draft = draft_mod.draft_reply(picked)
    print(f"[private] drafted reply {draft.action_id} (hash {draft.content_hash()})")
    return DraftedContext(
        picked=picked,
        draft=draft,
        topic_label=topic_label_for(picked),
    )


def run_project(drafted: DraftedContext) -> PublicArtifactView:
    return PublicArtifactView.project(
        action_id=drafted.draft.action_id,
        action_kind="draft_reply",
        status="pending_review",
        private_contexts=[drafted.picked],
        private_drafts=[drafted.draft],
        public_urls=[],
        when=datetime.now(timezone.utc),
    )


def run_audit(
    *,
    verifier: BoundaryVerifier,
    drafted: DraftedContext,
    view: PublicArtifactView,
    projection_type: ProjectionType = "PublicArtifactView",
) -> BoundaryVerification:
    return verifier.verify(
        step="project_view",
        action_id=drafted.draft.action_id,
        projection_type=projection_type,
        topic_label=drafted.topic_label,
        private_contexts=[drafted.picked],
        private_drafts=[drafted.draft],
        public_view=view,
    )


def run_publish(
    *, drafted: DraftedContext, view: PublicArtifactView, audit: BoundaryVerification
) -> None:
    audit_session = guild_audit.open_audit_session(drafted.draft.action_id)
    if audit_session:
        print(f"[guild] audit session: {guild_audit.session_url(audit_session)}")
        guild_audit.record_boundary_crossing(
            audit_session,
            audit.as_guild_payload(),
        )
        view.public_refs.append(
            {
                "kind": "guild_audit_session",
                "url": guild_audit.session_url(audit_session),
            }
        )
    else:
        print("[guild] audit skipped (CLI unavailable)")

    public_store.publish_evidence(view)
    print(f"[boundary] projected to public:evidence:{view.action_id}")
    print(f"[boundary] topic_label (non-revealing): '{drafted.topic_label}'")

    # Second public-plane write: InsForge Postgres under RLS. The edge
    # function verifies the JWT, inserts with user_id = auth.uid(), and
    # logs the boundary crossing + Guild session for external audit.
    guild_url_val = guild_audit.session_url(audit_session) if audit_session else None
    try:
        ins_result = insforge_publish.publish_to_insforge(
            view,
            private_field_count=audit.private_field_count,
            leak_check_passed=audit.leak_check_passed,
            guild_session_id=audit_session if audit_session else None,
            guild_url=guild_url_val,
        )
        print(f"[insforge] persisted action row {ins_result.get('action_row_id')}")
    except insforge_publish.InsforgePublishError as exc:
        print(f"[insforge] skipped: {exc}")


def run(*, verifier: BoundaryVerifier | None = None) -> dict:
    verifier = verifier or SharedBoundaryVerifier()

    try:
        observed = run_observe()
    except Exception as exc:
        return {
            "status": "observe_failed",
            "step": "observe",
            "error": str(exc),
        }

    if not observed.stale_thread_ids:
        print("[agent] nothing to do")
        return {"status": "noop"}

    try:
        drafted = run_draft(observed)
        view = run_project(drafted)
    except Exception as exc:
        return {
            "status": "draft_failed",
            "step": "draft",
            "error": str(exc),
        }

    try:
        audit = run_audit(verifier=verifier, drafted=drafted, view=view)
    except BoundaryVerificationError as exc:
        return {
            "status": "verify_failed",
            "step": "audit",
            "error": str(exc),
            "action_id": drafted.draft.action_id,
        }

    try:
        run_publish(drafted=drafted, view=view, audit=audit)
    except Exception as exc:
        return {
            "status": "publish_failed",
            "step": "publish",
            "error": str(exc),
            "action_id": drafted.draft.action_id,
        }

    try:
        review = human_review.request_review(drafted.draft, drafted.topic_label)
    except Exception as exc:
        return {
            "status": "review_failed",
            "step": "review",
            "error": str(exc),
            "action_id": drafted.draft.action_id,
        }

    print(f"[public] review handoff mode={review.get('mode')}")

    private_store.append_action_log(
        drafted.draft.action_id,
        {"step": "agent_complete", "picked": drafted.picked.thread_id},
    )

    return {
        "status": "published",
        "action_id": drafted.draft.action_id,
        "view": view.model_dump(),
        "review": review,
        "picked_thread_id": drafted.picked.thread_id,
        "private_field_count": audit.private_field_count,
        "public_field_count": audit.public_field_count,
        "leak_check_passed": audit.leak_check_passed,
        "contains_private_body": audit.contains_private_body,
    }


if __name__ == "__main__":
    run()
