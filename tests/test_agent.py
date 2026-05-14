"""Agent orchestration tests for failure modes and boundary verification wiring."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from proof_of_action import agent
from proof_of_action.boundary import PrivateContext, PrivateDraft, PublicArtifactView
from proof_of_action.boundary_verifier import (
    BoundaryVerificationError,
    SharedBoundaryVerifier,
)


def _thread() -> PrivateContext:
    return PrivateContext(
        thread_id="t_001",
        subject="sample stale thread",
        from_email="jamie@example.com",
        from_name="Jamie",
        body="We should meet about the proposal this quarter.",
        participants=["jamie@example.com", "alex@example.com"],
        last_message_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _draft(action_id: str = "act_001") -> PrivateDraft:
    return PrivateDraft(
        action_id=action_id,
        thread_id="t_001",
        body="Hi Alex, I can follow up tomorrow.",
        model="test",
        generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def _seed_observe(monkeypatch, context: PrivateContext, draft: PrivateDraft) -> None:
    monkeypatch.setattr(agent, "load_fixture", lambda: [context])
    monkeypatch.setattr(agent.private_store, "save_thread", lambda _: None)
    monkeypatch.setattr(agent.draft_mod, "classify_stale", lambda _: ["t_001"])
    monkeypatch.setattr(agent.draft_mod, "draft_reply", lambda _: draft)


def test_boundary_verifier_rejects_leaky_public_projection() -> None:
    ctx = _thread()
    draft = _draft()
    view = PublicArtifactView.project(
        action_id=draft.action_id,
        action_kind="draft_reply",
        status="pending_review",
        private_contexts=[ctx],
        private_drafts=[draft],
        public_urls=[{"kind": "raw", "url": ctx.body}],
        when=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    verifier = SharedBoundaryVerifier()
    with pytest.raises(BoundaryVerificationError, match="public projection leaks"):
        verifier.verify(
            step="project_view",
            action_id=draft.action_id,
            projection_type="PublicArtifactView",
            topic_label="a follow-up",
            private_contexts=[ctx],
            private_drafts=[draft],
            public_view=view,
        )


def test_shared_verifier_counts_are_stable_for_clean_projection() -> None:
    ctx = _thread()
    draft = _draft()
    view = PublicArtifactView.project(
        action_id=draft.action_id,
        action_kind="draft_reply",
        status="pending_review",
        private_contexts=[ctx],
        private_drafts=[draft],
        public_urls=[],
        when=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    verification = SharedBoundaryVerifier().verify(
        step="project_view",
        action_id=draft.action_id,
        projection_type="PublicArtifactView",
        topic_label="a follow-up",
        private_contexts=[ctx],
        private_drafts=[draft],
        public_view=view,
    )

    assert verification.step == "project_view"
    assert verification.private_field_count == (
        len(ctx.body.split()) + len(ctx.participants) + len(draft.body.split())
    )
    assert verification.public_field_count == len(view.private_refs)
    assert verification.leak_check_passed is True


class _FailingVerifier:
    def verify(
        self,
        *,  # pragma: no cover
        step: str,
        action_id: str,
        projection_type: str,
        topic_label: str,
        private_contexts: list[PrivateContext],
        private_drafts: list[PrivateDraft],
        public_view: PublicArtifactView,
    ) -> None:
        raise BoundaryVerificationError("forced verifier failure")


def test_agent_run_handles_verifier_failure(monkeypatch) -> None:
    context = _thread()
    draft = _draft()
    _seed_observe(monkeypatch, context, draft)

    result = agent.run(verifier=_FailingVerifier())

    assert result["status"] == "verify_failed"
    assert result["step"] == "audit"


def test_agent_run_handles_draft_failure(monkeypatch) -> None:
    context = _thread()

    monkeypatch.setattr(agent, "load_fixture", lambda: [context])
    monkeypatch.setattr(agent.private_store, "save_thread", lambda _: None)
    monkeypatch.setattr(agent.draft_mod, "classify_stale", lambda _: ["t_001"])
    monkeypatch.setattr(
        agent.draft_mod,
        "draft_reply",
        lambda _: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = agent.run()

    assert result["status"] == "draft_failed"
    assert result["step"] == "draft"


def test_agent_run_handles_publish_failure(monkeypatch) -> None:
    context = _thread()
    draft = _draft()
    _seed_observe(monkeypatch, context, draft)
    monkeypatch.setattr(
        agent.public_store,
        "publish_evidence",
        lambda _: (_ for _ in ()).throw(RuntimeError("nop")),
    )

    result = agent.run()

    assert result["status"] == "publish_failed"
    assert result["step"] == "publish"
