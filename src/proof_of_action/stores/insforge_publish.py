"""Public-plane persistence via InsForge.

Sits alongside public_store.py (Redis). Both are public-plane writers — the
Redis one is the infra-layer ACL proof for demos, this one lands the typed
view in Postgres under RLS so each user only ever sees their own rows.

Flow: sign in with POA_INSFORGE_EMAIL/PASSWORD → cache JWT → POST the view
to the finalize-action edge function with Bearer <JWT>. The edge function
verifies the user and inserts under RLS.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from proof_of_action.boundary import PublicArtifactView

BASE_URL = os.environ.get(
    "POA_INSFORGE_URL", "https://q7haa32f.us-east.insforge.app"
).rstrip("/")
EMAIL = os.environ.get("POA_INSFORGE_EMAIL")
PASSWORD = os.environ.get("POA_INSFORGE_PASSWORD")

_cached_token: str | None = None


class InsforgePublishError(RuntimeError):
    pass


def _sign_in() -> str:
    if not EMAIL or not PASSWORD:
        raise InsforgePublishError(
            "POA_INSFORGE_EMAIL / POA_INSFORGE_PASSWORD not set"
        )
    resp = httpx.post(
        f"{BASE_URL}/api/auth/sessions",
        params={"client_type": "server"},
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10,
    )
    if resp.status_code != 200:
        raise InsforgePublishError(f"sign-in failed: {resp.status_code} {resp.text}")
    token = resp.json().get("accessToken")
    if not token:
        raise InsforgePublishError("sign-in returned no accessToken")
    return token


def _token() -> str:
    global _cached_token
    if _cached_token is None:
        _cached_token = _sign_in()
    return _cached_token


def send_review_email(to_address: str, action_id: str, topic_label: str) -> dict:
    """Notify the operator that a draft is queued for human review.

    Carries ONLY the topic_label (already non-revealing) and the action_id
    hash — never the draft body or private thread content. This is a public
    -plane projection, same trust level as the OpenhumanView handoff.
    """
    resp = httpx.post(
        f"{BASE_URL}/api/emails/send",
        headers={"Authorization": f"Bearer {_token()}"},
        json={
            "to": to_address,
            "subject": f"[proof-of-action] draft {action_id} is awaiting your review",
            "html": (
                f"<p>An agent run produced a draft queued for your review.</p>"
                f"<ul>"
                f"<li><strong>action_id:</strong> <code>{action_id}</code></li>"
                f"<li><strong>topic:</strong> {topic_label}</li>"
                f"</ul>"
                f"<p>Private content stays on your machine. This email contains "
                f"only the redacted topic label and action identifier — no "
                f"thread body, recipient names, or draft contents.</p>"
            ),
        },
        timeout=10,
    )
    return {"status": resp.status_code, "body": resp.text[:200]}


def publish_to_insforge(
    view: PublicArtifactView,
    *,
    projection_type: str = "PublicArtifactView",
    private_field_count: int,
    leak_check_passed: bool,
    guild_session_id: str | None = None,
    guild_url: str | None = None,
) -> dict[str, Any]:
    """POST the typed public view to the finalize-action edge function.

    `private_field_count` is the count of private fields that were collapsed
    into the projection (used for the boundary_crossings audit row).
    """
    body: dict[str, Any] = {
        "public_view": {
            "action_id": view.action_id,
            "action_kind": view.action_kind,
            "day": view.day,
            "status": view.status,
            "public_refs": {"items": view.public_refs},
            "cited_md": "",
        },
        "crossing": {
            "projection_type": projection_type,
            "private_field_count": private_field_count,
            "public_field_count": len(view.public_refs) + len(view.private_refs),
            "leak_check_passed": leak_check_passed,
        },
    }
    if guild_session_id and guild_url:
        body["guild"] = {"session_id": guild_session_id, "url": guild_url}

    resp = httpx.post(
        f"{BASE_URL}/functions/finalize-action",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15,
    )
    if resp.status_code == 401:
        # Token may have expired — re-sign once and retry.
        global _cached_token
        _cached_token = None
        resp = httpx.post(
            f"{BASE_URL}/functions/finalize-action",
            headers={
                "Authorization": f"Bearer {_token()}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=15,
        )
    if resp.status_code >= 400:
        raise InsforgePublishError(
            f"finalize-action failed: {resp.status_code} {resp.text}"
        )
    return resp.json()
