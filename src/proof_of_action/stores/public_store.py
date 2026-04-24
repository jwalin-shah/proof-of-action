"""Public keyspace — agent_public Redis user. ACL rejects writes to private:*.

If boundary logic ever accidentally tries to publish private data via this
client, Redis itself rejects it with NOPERM. That's the infrastructural
guarantee that makes the privacy boundary provable.
"""
from __future__ import annotations

import os

import redis

from proof_of_action.boundary import PublicArtifactView

PORT = int(os.environ.get("REDIS_PORT", "6390"))
PW = os.environ.get("REDIS_PUBLIC_PW", "pubpw")


def client() -> redis.Redis:
    return redis.Redis(
        host="localhost",
        port=PORT,
        db=0,
        username="agent_public",
        password=PW,
        decode_responses=True,
    )


def publish_evidence(view: PublicArtifactView) -> None:
    r = client()
    r.set(f"public:evidence:{view.action_id}", view.model_dump_json())


def all_evidence() -> list[PublicArtifactView]:
    r = client()
    out = []
    for key in r.scan_iter("public:evidence:*"):
        data = r.get(key)
        if data:
            out.append(PublicArtifactView.model_validate_json(data))
    return out
