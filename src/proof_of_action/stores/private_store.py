"""Private keyspace — only the agent_private Redis user can touch this.

Redis ACL blocks writes to private:* from the public client and vice versa.
The privacy boundary is enforced at the infra layer, not just app logic.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import redis

from proof_of_action.boundary import PrivateContext, PrivateDraft
from proof_of_action import crypto

PORT = int(os.environ.get("REDIS_PORT", "6390"))
PW = os.environ.get("REDIS_PRIVATE_PW", "privpw")

# Phase G7: every private:* value is wrapped with AES-GCM before SET and
# unwrapped on GET. A .rdb dump or a SHOW-COMMAND leak yields ciphertext.
# POA_ENVELOPE=off disables it for local dev / migration.
ENVELOPE_ENABLED = os.environ.get("POA_ENVELOPE", "on").lower() != "off"

# Phase G6: mTLS to Redis. When POA_REDIS_TLS=on, the client presents
# private/tls/agent.{crt,key} and pins private/tls/ca.crt. Paired with the
# ACL password, a leaked .env alone still can't reach private:* — you also
# need the agent client cert off the operator's disk.
TLS_ENABLED = os.environ.get("POA_REDIS_TLS", "off").lower() == "on"
TLS_CA = os.environ.get("POA_REDIS_TLS_CA", "private/tls/ca.crt")
TLS_CERT = os.environ.get("POA_REDIS_TLS_CERT", "private/tls/agent.crt")
TLS_KEY = os.environ.get("POA_REDIS_TLS_KEY", "private/tls/agent.key")


def client() -> redis.Redis:
    # decode_responses=False so binary envelope bytes survive round-trip.
    # Callers that still want text decode explicitly after _unwrap_value.
    kwargs = dict(
        host="localhost",
        port=PORT,
        db=0,
        username="agent_private",
        password=PW,
        decode_responses=False,
    )
    if TLS_ENABLED:
        kwargs.update(
            ssl=True,
            ssl_ca_certs=TLS_CA,
            ssl_certfile=TLS_CERT,
            ssl_keyfile=TLS_KEY,
            ssl_cert_reqs="required",
        )
    return redis.Redis(**kwargs)


def _derivation_id_for(key: str) -> str | None:
    """Extract the natural isolation id from a private:* Redis key.

    H4: each unit of private data (thread, draft, action log) gets its own
    HKDF-derived key scoped by the id embedded in the Redis key. Leaking
    the key for action X cannot decrypt action Y.

        private:thread:<thread_id>      → thread_id
        private:draft:<action_id>       → action_id
        private:action_log:<action_id>  → action_id
    """
    parts = key.split(":", 2)
    if len(parts) == 3 and parts[0] == "private":
        return parts[2]
    return None


def _wrap_value(key: str, plaintext: str) -> bytes:
    if not ENVELOPE_ENABLED:
        return plaintext.encode()
    # AAD binds the ciphertext to the Redis key so swapping envelopes
    # between keys fails GCM auth. H4: prefer per-id HKDF-derived key;
    # fall back to master for values without a clean id in their key.
    derivation_id = _derivation_id_for(key)
    pt = plaintext.encode()
    aad = key.encode()
    if derivation_id:
        return crypto.encrypt_derived(derivation_id, pt, aad=aad)
    return crypto.encrypt_with_master(pt, aad=aad)


def _unwrap_value(key: str, stored: bytes | None) -> str | None:
    if stored is None:
        return None
    if not ENVELOPE_ENABLED:
        return stored.decode()
    # Legacy: pre-G7 values start with '{' (JSON). Decrypt otherwise, routing
    # on the envelope version byte: 0x01 master, 0x02 derived (H4).
    if stored[:1] == b"{":
        return stored.decode()
    aad = key.encode()
    version = crypto.envelope_version(stored)
    if version == crypto.VERSION_DERIVED:
        derivation_id = _derivation_id_for(key)
        if not derivation_id:
            raise crypto.EnvelopeCorrupt(
                f"derived envelope needs id but key has no id shape: {key}"
            )
        return crypto.decrypt_derived(derivation_id, stored, aad=aad).decode()
    return crypto.decrypt_with_master(stored, aad=aad).decode()


def save_thread(ctx: PrivateContext) -> None:
    r = client()
    key = f"private:thread:{ctx.thread_id}"
    r.set(key, _wrap_value(key, ctx.model_dump_json()), ex=60 * 60 * 24)


def load_thread(thread_id: str) -> PrivateContext:
    r = client()
    key = f"private:thread:{thread_id}"
    data = _unwrap_value(key, r.get(key))
    if not data:
        raise KeyError(thread_id)
    return PrivateContext.model_validate_json(data)


def all_threads() -> list[PrivateContext]:
    r = client()
    out = []
    for key in r.scan_iter("private:thread:*"):
        key_str = key.decode() if isinstance(key, bytes) else key
        data = _unwrap_value(key_str, r.get(key))
        if data:
            out.append(PrivateContext.model_validate_json(data))
    return out


def save_draft(draft: PrivateDraft) -> None:
    r = client()
    key = f"private:draft:{draft.action_id}"
    r.set(key, _wrap_value(key, draft.model_dump_json()), ex=60 * 60 * 24 * 7)


def all_drafts() -> list[PrivateDraft]:
    """Load every PrivateDraft in the private keyspace.

    Use this instead of raw r.get/scan_iter in tests and scripts so envelope
    unwrapping stays centralized.
    """
    r = client()
    out: list[PrivateDraft] = []
    for key in r.scan_iter("private:draft:*"):
        key_str = key.decode() if isinstance(key, bytes) else key
        data = _unwrap_value(key_str, r.get(key))
        if data:
            out.append(PrivateDraft.model_validate_json(data))
    return out


def append_action_log(action_id: str, entry: dict) -> None:
    r = client()
    key = f"private:action_log:{action_id}"
    entry = {**entry, "ts": datetime.now(timezone.utc).isoformat()}
    r.rpush(key, _wrap_value(key, json.dumps(entry)))
    r.expire(key, 60 * 60 * 24 * 30)
