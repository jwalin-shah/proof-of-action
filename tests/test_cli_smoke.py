"""Smoke contract for the package CLI entrypoint."""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
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


def test_publish_default_writes_to_ignored_runtime_path(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("POA_CITED_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    from scripts import publish

    publish = importlib.reload(publish)
    repo_root = Path(__file__).resolve().parent.parent

    assert publish.DEFAULT_OUT == Path("artifacts/runtime/cited.md")
    assert publish.OUT == publish.DEFAULT_OUT
    assert "artifacts/runtime/" in (repo_root / ".gitignore").read_text()
