"""LLM-backed draft generation.

Three backends, selected by env:
  POA_LLM=anthropic  (default)  — Anthropic Claude, trusted inside the TCB
  POA_LLM=ollama               — Ollama over HTTP (local or Akash GPU deploy)
                                  Removes Anthropic from the TCB entirely;
                                  the Ollama endpoint is operator-controlled.
  (no key, no endpoint)        — deterministic local template fallback

The ollama backend is protocol-compatible with any /api/chat-speaking
endpoint. Drop-in alternatives for users who want stronger privacy
guarantees than a commodity API:
  - Venice.ai (non-logging managed inference)
  - Near AI (decentralized inference over the NEAR protocol)
  - vLLM / TGI / LM Studio on your own hardware
All four fall under the 'remote_ollama_operator_hosted' TCB label when
the endpoint is non-localhost; override with POA_TCB_LABEL if you want
to surface the provider name in the action log.

Sensitivity-tagged: the prompt carries private content so every call is
logged as a private-zone boundary crossing. The target TCB differs by
backend and is recorded in the action log.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import httpx
from anthropic import Anthropic

from proof_of_action.boundary import (
    PrivateContext,
    PrivateDraft,
    redact_for_llm,
)
from proof_of_action.stores import private_store

MODEL = "claude-sonnet-4-6"
OLLAMA_MODEL = os.environ.get("POA_OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_URL = os.environ.get("POA_OLLAMA_URL", "")


def _draft_via_ollama(redacted: dict) -> tuple[str, str, str]:
    """Draft via Ollama /api/chat. Returns (body, model_used, tcb_label)."""
    url = OLLAMA_URL.rstrip("/") + "/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You draft short, warm professional replies. "
                    "Reply from 'Jamie'. One short paragraph + signoff. "
                    "No confidential details. No commitments."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Draft a reply to this stale thread:\n\n"
                    f"Subject: {redacted['subject']}\n"
                    f"Last message: {redacted['last_message_at']}\n"
                    f"Body: {redacted['body']}"
                ),
            },
        ],
    }
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    body = data.get("message", {}).get("content", "").strip()
    # TCB label: operator-chosen label wins; else default to local vs remote.
    # Any non-localhost endpoint is treated as an operator-controlled remote
    # (Akash, Runpod, their own rented box — same trust model: YOU picked
    # the provider, not a big AI company).
    tcb = os.environ.get("POA_TCB_LABEL")
    if not tcb:
        u = OLLAMA_URL.lower()
        if "localhost" in u or "127.0.0.1" in u or "://[::1]" in u:
            tcb = "local_ollama"
        else:
            tcb = "remote_ollama_operator_hosted"
    return body, f"ollama:{OLLAMA_MODEL}", tcb


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

    # Backend selection: explicit POA_LLM wins; else POA_OLLAMA_URL → ollama;
    # else ANTHROPIC_API_KEY → anthropic; else template fallback.
    backend = os.environ.get("POA_LLM", "").lower().strip()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not backend:
        if OLLAMA_URL:
            backend = "ollama"
        elif key:
            backend = "anthropic"
        else:
            backend = "template"

    # Initial TCB label (may be refined by the ollama backend below using
    # POA_TCB_LABEL or localhost detection).
    if backend == "ollama":
        u = OLLAMA_URL.lower()
        tcb_label = os.environ.get("POA_TCB_LABEL") or (
            "local_ollama"
            if ("localhost" in u or "127.0.0.1" in u or "://[::1]" in u)
            else "remote_ollama_operator_hosted"
        )
    else:
        tcb_label = {
            "anthropic": "anthropic_tcb",
            "template": "no_llm",
        }.get(backend, "anthropic_tcb")

    private_store.append_action_log(
        action_id,
        {
            "step": "draft_start",
            "sensitivity": "private",
            "crosses_to": tcb_label,
            "backend": backend,
            "thread_hash": ctx.content_hash(),
        },
    )

    redacted = redact_for_llm(ctx)
    if backend == "ollama":
        body, model_used, tcb_label = _draft_via_ollama(redacted)
    elif backend == "anthropic":
        client = Anthropic(api_key=key)
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
    else:
        body = (
            f"Hi {ctx.from_name.split()[0]},\n\n"
            f"Thanks for your note on '{ctx.subject}'. Apologies for the late "
            f"reply — wanted to circle back now that I've had a chance to review. "
            f"Happy to pick this up again; proposing a call next week.\n\n"
            f"Best,\nJamie"
        )
        model_used = "local_template_fallback"

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
