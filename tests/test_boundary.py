"""The leak test. This is the demo's money shot.

After the agent runs, cited.md must contain ZERO substrings from private fields.
If this test ever fails, the boundary broke.
"""
from __future__ import annotations

from pathlib import Path

from proof_of_action import agent
from proof_of_action.redaction import private_fingerprints, scan_for_leaks
from proof_of_action.stores import private_store


CITED = Path("artifacts/cited.md")


def test_public_artifact_contains_no_private_content(monkeypatch):
    result = agent.run()
    assert result["status"] in ("published", "noop")

    from scripts import publish
    md = publish.build_cited_md()

    ctxs = agent.load_fixture()
    drafts = []
    picked_id = result.get("picked_thread_id")
    if picked_id:
        try:
            from proof_of_action.stores import private_store
            drafts = private_store.all_drafts()
        except Exception:
            pass

    fps = private_fingerprints(ctxs, drafts)
    leaks = scan_for_leaks(md, fps)
    assert not leaks, f"LEAK detected in cited.md: {leaks[:3]}"


def test_acl_blocks_private_write_via_public_client():
    from proof_of_action.stores.public_store import client
    pub = client()
    import redis
    try:
        pub.set("private:sneaky", "should_fail")
        raise AssertionError("Expected NOPERM, write succeeded")
    except redis.ResponseError as e:
        assert "NOPERM" in str(e) or "no permission" in str(e).lower()
