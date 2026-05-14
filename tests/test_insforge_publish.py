from __future__ import annotations

from datetime import datetime, timezone

from proof_of_action.boundary import PrivateContext, PrivateDraft, PublicArtifactView
from proof_of_action.stores import insforge_publish


def test_insforge_publish_uses_public_artifact_boundary_reference_count(monkeypatch):
    ctx = PrivateContext(
        thread_id="t_001",
        subject="sample stale thread",
        from_email="jamie@example.com",
        from_name="Jamie",
        body="We should meet about the proposal this quarter.",
        participants=["jamie@example.com", "alex@example.com"],
        last_message_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    draft = PrivateDraft(
        action_id="act_001",
        thread_id="t_001",
        body="Hi Alex, I can follow up tomorrow.",
        model="test",
        generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    view = PublicArtifactView.project(
        action_id=draft.action_id,
        action_kind="draft_reply",
        status="pending_review",
        private_contexts=[ctx],
        private_drafts=[draft],
        public_urls=[{"kind": "runbook", "url": "https://example.test/runbook"}],
        when=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    captured: dict = {}

    class _Response:
        status_code = 200
        text = "{}"

        def json(self) -> dict:
            return {"action_row_id": "row_001"}

    def fake_post(*args, **kwargs):
        captured["json"] = kwargs["json"]
        return _Response()

    monkeypatch.setattr(insforge_publish, "_token", lambda: "test-token")
    monkeypatch.setattr(insforge_publish.httpx, "post", fake_post)

    result = insforge_publish.publish_to_insforge(
        view,
        private_field_count=11,
        leak_check_passed=True,
    )

    assert result == {"action_row_id": "row_001"}
    assert captured["json"]["crossing"]["public_field_count"] == (
        view.boundary_reference_count()
    )
