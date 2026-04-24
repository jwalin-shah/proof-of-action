"""One-command judge demo.

    $ python scripts/demo.py

Runs the full pipeline, prints every boundary crossing, ends with the leak
test result. Each step tells the story out loud.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def banner(s: str) -> None:
    print()
    print("=" * 72)
    print(f"  {s}")
    print("=" * 72)


def main() -> int:
    banner("1. reset redis keyspaces (private + public)")
    subprocess.run(
        [
            "redis-cli", "-p", "6390", "--user", "default",
            "FLUSHDB",
        ],
        check=False,
        cwd=ROOT,
    )

    banner("2. reapply ACL (two-user boundary)")
    subprocess.run(["bash", "scripts/setup_redis.sh"], check=True, cwd=ROOT)

    banner("3. run agent — observe, classify, draft, project, publish")
    from proof_of_action import agent
    result = agent.run()
    print()
    print(f"  → action_id: {result.get('action_id')}")

    banner("4. generate cited.md (redacted, hashed, batched)")
    from scripts import publish
    publish.main()

    banner("5. leak test — scan cited.md for any private field")
    r = subprocess.run(
        ["python", "-m", "pytest", "tests/test_boundary.py", "-v", "--no-header"],
        cwd=ROOT,
    )

    banner("6. review audit log (private side — operator-only)")
    subprocess.run(
        [
            "redis-cli", "-p", "6390",
            "--user", "agent_private", "--pass", "privpw",
            "--no-auth-warning",
            "LRANGE", f"private:action_log:{result.get('action_id')}", "0", "-1",
        ],
        cwd=ROOT,
    )

    banner("DONE")
    print("  Public artifact: artifacts/cited.md")
    print("  Private artifacts: private/ (gitignored) + redis private:* (ACL'd)")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
