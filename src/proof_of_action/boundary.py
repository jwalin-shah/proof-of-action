"""The privacy boundary.

Every outbound call — Guild, openhuman, cited.md, any sponsor — goes through
a typed projection defined here. Raw PrivateContext never crosses a zone.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Sensitivity = Literal["private", "public"]

# Per-deployment pepper mixed into every content_hash. Without this, the
# sha256 refs in cited.md would be vulnerable to dictionary/rainbow attacks
# since thread bodies or emails are often low-entropy. The pepper is never
# published; it stays on the operator's machine.
HASH_PEPPER = os.environ.get("HASH_PEPPER", "dev-pepper-change-me")


class PrivateContext(BaseModel):
    """Full-fidelity private data. Lives only in the private zone."""

    thread_id: str
    subject: str
    from_email: str
    from_name: str
    body: str
    participants: list[str]
    last_message_at: datetime

    def content_hash(self) -> str:
        payload = f"{HASH_PEPPER}|thread|{self.thread_id}:{self.from_email}:{self.body}"
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()[:32]


class PrivateDraft(BaseModel):
    action_id: str
    thread_id: str
    body: str
    model: str
    generated_at: datetime

    def content_hash(self) -> str:
        payload = f"{HASH_PEPPER}|draft|{self.action_id}:{self.body}"
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()[:32]


class VapiView(BaseModel):
    """What a Vapi voice agent is allowed to read out loud.

    NO body. NO participant emails. NO draft content. Only an opaque topic
    label, action_id for callback, and a TTS-safe script.
    """

    action_id: str
    topic_label: str = Field(
        description="Redacted label: 'a professional follow-up', 'a personal reply'"
    )
    script: str = Field(description="Exact phrase the voice agent will read")

    @classmethod
    def project(cls, draft: PrivateDraft, topic_label: str) -> "VapiView":
        return cls(
            action_id=draft.action_id,
            topic_label=topic_label,
            script=(
                f"Hello. A draft for {topic_label} is ready for your review. "
                f"Reference {draft.action_id}. This message contains no private content."
            ),
        )


class OpenhumanView(BaseModel):
    """Result view for upstream agent platforms (e.g. openhuman).

    Tells the platform what happened, not what was in it.
    """

    action_id: str
    action_kind: Literal["draft_reply", "schedule_followup", "noop"]
    status: Literal["pending_review", "sent", "skipped"]
    public_evidence_refs: list[str] = Field(
        description="sha256 hashes of private items referenced"
    )


class PublicArtifactView(BaseModel):
    """What lands in cited.md. Aggressively redacted."""

    action_id: str
    action_kind: str
    day: str = Field(description="YYYY-MM-DD — day-granularity, not timestamp")
    private_refs: list[dict]
    public_refs: list[dict]
    status: str

    @classmethod
    def project(
        cls,
        *,
        action_id: str,
        action_kind: str,
        status: str,
        private_contexts: list[PrivateContext],
        private_drafts: list[PrivateDraft],
        public_urls: list[dict],
        when: datetime,
    ) -> "PublicArtifactView":
        refs: list[dict] = []
        for ctx in private_contexts:
            refs.append({"kind": "inbox_thread", "hash": ctx.content_hash()})
        for drf in private_drafts:
            refs.append({"kind": "draft", "hash": drf.content_hash()})
        return cls(
            action_id=action_id,
            action_kind=action_kind,
            day=when.astimezone(timezone.utc).strftime("%Y-%m-%d"),
            private_refs=refs,
            public_refs=public_urls,
            status=status,
        )


def redact_for_llm(ctx: PrivateContext) -> dict:
    """Minimize what we send to Anthropic for the draft step.

    We accept Anthropic as inside the reasoning TCB but still practice minimization.
    """
    return {
        "thread_id": ctx.thread_id,
        "subject": ctx.subject,
        "body": ctx.body,
        "sender_role": "external_contact",
        "last_message_at": ctx.last_message_at.isoformat(),
    }


def topic_label_for(ctx: PrivateContext) -> str:
    """Generate a non-revealing label for voice/public use.

    Previous versions returned category-specific labels (recruiting,
    fundraising, billing, speaking). That is still semantic disclosure: a
    reviewer would learn the *kind* of thing the operator is doing. We
    collapse to a single uniform label. If you ever need a richer label,
    emit it only to the private side — never to a public projection.
    """
    return "a follow-up"
