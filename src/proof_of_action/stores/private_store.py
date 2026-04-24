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

PORT = int(os.environ.get("REDIS_PORT", "6390"))
PW = os.environ.get("REDIS_PRIVATE_PW", "privpw")


def client() -> redis.Redis:
    return redis.Redis(
        host="localhost",
        port=PORT,
        db=0,
        username="agent_private",
        password=PW,
        decode_responses=True,
    )


def save_thread(ctx: PrivateContext) -> None:
    r = client()
    r.set(
        f"private:thread:{ctx.thread_id}",
        ctx.model_dump_json(),
        ex=60 * 60 * 24,
    )


def load_thread(thread_id: str) -> PrivateContext:
    r = client()
    data = r.get(f"private:thread:{thread_id}")
    if not data:
        raise KeyError(thread_id)
    return PrivateContext.model_validate_json(data)


def all_threads() -> list[PrivateContext]:
    r = client()
    out = []
    for key in r.scan_iter("private:thread:*"):
        out.append(PrivateContext.model_validate_json(r.get(key)))
    return out


def save_draft(draft: PrivateDraft) -> None:
    r = client()
    r.set(
        f"private:draft:{draft.action_id}",
        draft.model_dump_json(),
        ex=60 * 60 * 24 * 7,
    )


def append_action_log(action_id: str, entry: dict) -> None:
    r = client()
    entry = {**entry, "ts": datetime.now(timezone.utc).isoformat()}
    r.rpush(f"private:action_log:{action_id}", json.dumps(entry))
    r.expire(f"private:action_log:{action_id}", 60 * 60 * 24 * 30)
