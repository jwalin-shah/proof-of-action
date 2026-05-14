"""Smoke contract for the package CLI entrypoint."""
from __future__ import annotations

import json
import os
import subprocess
import sys


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("POA_FIXTURE", None)
    env.pop("POA_SOURCE", None)
    return env


def test_agent_cli_smoke_runs_without_services_or_secrets() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "proof_of_action.agent", "--smoke"],
        check=False,
        capture_output=True,
        env=_clean_env(),
        text=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "entrypoint": "proof_of_action.agent",
        "fixture": "fixtures/sample_threads.json",
        "source": "fixture",
        "status": "ok",
    }
    assert result.stderr == ""


def test_agent_cli_bad_input_reports_clear_failure() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "proof_of_action.agent", "--definitely-not-real"],
        check=False,
        capture_output=True,
        env=_clean_env(),
        text=True,
    )

    assert result.returncode == 2
    assert "unrecognized arguments: --definitely-not-real" in result.stderr
