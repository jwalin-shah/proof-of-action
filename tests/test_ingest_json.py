"""Tests for local JSON ingestion into the private boundary."""
from __future__ import annotations

import json

from scripts import ingest_json


def _valid_row() -> dict:
    return {
        "thread_id": "t_001",
        "subject": "Re: Staff SWE role",
        "from": "alex@example.com",
        "from_name": "Alex",
        "last_message_at": "2026-03-01T14:00:00Z",
        "body": "Following up.",
        "participants": ["jamie@example.com", "alex@example.com"],
    }


def test_ingest_json_accepts_valid_rows(monkeypatch, tmp_path, capsys) -> None:
    saved = []
    monkeypatch.setattr(ingest_json.private_store, "save_thread", saved.append)
    path = tmp_path / "threads.json"
    path.write_text(json.dumps([_valid_row()]))

    assert ingest_json.main(str(path)) == 0

    assert len(saved) == 1
    assert saved[0].thread_id == "t_001"
    assert saved[0].from_email == "alex@example.com"
    assert "ingested t_001" in capsys.readouterr().out


def test_ingest_json_rejects_missing_sender(monkeypatch, tmp_path, capsys) -> None:
    saved = []
    monkeypatch.setattr(ingest_json.private_store, "save_thread", saved.append)
    row = _valid_row()
    row.pop("from")
    path = tmp_path / "threads.json"
    path.write_text(json.dumps([row]))

    assert ingest_json.main(str(path)) == 2

    assert saved == []
    err = capsys.readouterr().err
    assert "row 0" in err
    assert "field 'from' or 'from_email' must be a non-empty string" in err


def test_ingest_json_rejects_non_object_rows(monkeypatch, tmp_path, capsys) -> None:
    saved = []
    monkeypatch.setattr(ingest_json.private_store, "save_thread", saved.append)
    path = tmp_path / "threads.json"
    path.write_text(json.dumps([_valid_row(), "not-a-record"]))

    assert ingest_json.main(str(path)) == 2

    assert saved == []
    assert "row 1 must be a thread record object" in capsys.readouterr().err
