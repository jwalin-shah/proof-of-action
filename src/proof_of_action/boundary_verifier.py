"""Shared boundary verification for public/private crossings.

This module centralizes the values that describe a boundary crossing.
It is intentionally small and deterministic so it can be reused by both
agent orchestration and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Protocol

from proof_of_action.boundary import PrivateContext, PrivateDraft, PublicArtifactView
from proof_of_action.redaction import private_fingerprints


ProjectionType = Literal["PublicArtifactView", "OpenhumanView", "VapiView"]


class BoundaryVerificationError(RuntimeError):
    """Boundary projection failed validation."""


@dataclass(frozen=True)
class BoundaryVerification:
    """Computed audit facts for a boundary projection."""

    step: str
    action_id: str
    projection_type: ProjectionType
    topic_label: str
    private_field_count: int
    public_field_count: int
    contains_private_body: bool
    leak_check_passed: bool

    def as_guild_payload(self) -> dict:
        return {
            "step": self.step,
            "action_id": self.action_id,
            "kind": self.projection_type,
            "topic_label": self.topic_label,
            "private_field_count": self.private_field_count,
            "public_field_count": self.public_field_count,
            "contains_private_body": self.contains_private_body,
            "leak_check_passed": self.leak_check_passed,
        }


class BoundaryVerifier(Protocol):
    """Contract for boundary-audit status verifiers."""

    def verify(
        self,
        *,
        step: str,
        action_id: str,
        projection_type: ProjectionType,
        topic_label: str,
        private_contexts: Iterable[PrivateContext],
        private_drafts: Iterable[PrivateDraft],
        public_view: PublicArtifactView,
    ) -> BoundaryVerification: ...


class SharedBoundaryVerifier:
    """Project verification shared by agent orchestration and tests."""

    def verify(
        self,
        *,
        step: str,
        action_id: str,
        projection_type: ProjectionType,
        topic_label: str,
        private_contexts: Iterable[PrivateContext],
        private_drafts: Iterable[PrivateDraft],
        public_view: PublicArtifactView,
    ) -> BoundaryVerification:
        private_contexts_list = list(private_contexts)
        private_drafts_list = list(private_drafts)

        private_field_count = sum(
            len(ctx.body.split()) + len(ctx.participants) for ctx in private_contexts_list
        ) + sum(len(d.body.split()) for d in private_drafts_list)

        public_field_count = len(public_view.private_refs) + len(public_view.public_refs)

        fingerprints = private_fingerprints(private_contexts_list, private_drafts_list)
        serialized = public_view.model_dump_json()
        contains_private_body = any(fp in serialized for fp in fingerprints)
        leak_check_passed = not contains_private_body

        if not leak_check_passed:
            raise BoundaryVerificationError(
                "public projection leaks private material into public view"
            )

        return BoundaryVerification(
            step=step,
            action_id=action_id,
            projection_type=projection_type,
            topic_label=topic_label,
            private_field_count=private_field_count,
            public_field_count=public_field_count,
            contains_private_body=contains_private_body,
            leak_check_passed=leak_check_passed,
        )
