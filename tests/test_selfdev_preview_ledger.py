"""Isolated SQLite replay tests: no production database or device touched."""

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import json
import os
import sqlite3

import pytest

from core.selfdev_preview_ledger import InspectionReplayLedger
from core.selfdev_request_protocol import parse_inspection_request


NOW = 1_800_000_000


def _request(request_id="a" * 32, digest_hash="0" * 64, expires=NOW + 60):
    return parse_inspection_request(
        json.dumps({
            "version": 1,
            "action": "inspect_candidate",
            "request_id": request_id,
            "revision": "b" * 40,
            "expires_unix": expires,
            "files": [{"path": "core/example.py", "sha256": digest_hash}],
        }).encode("utf-8"),
        now_unix=NOW,
    )


def _claim_from_process(arguments):
    path, request_id = arguments
    return InspectionReplayLedger(path).claim(
        _request(request_id), now_unix=NOW
    ).status


def test_record_then_replay_across_instances_without_authorizing(tmp_path):
    path = tmp_path / "replay.db"
    result = InspectionReplayLedger(path).claim(_request(), now_unix=NOW)
    assert result.status == "recorded_for_inspection"
    assert result.authorizes_mutation is False
    assert result.requires_human_approval is True
    repeat = InspectionReplayLedger(path).claim(_request(), now_unix=NOW)
    assert repeat.status == "already_seen"
    assert repeat.authorizes_mutation is False
    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT count(*) FROM inspected_requests"
        ).fetchone()[0] == 1


def test_reused_request_id_with_different_manifest_is_rejected(tmp_path):
    ledger = InspectionReplayLedger(tmp_path / "replay.db")
    assert ledger.claim(_request(), now_unix=NOW).status == "recorded_for_inspection"
    altered = _request(digest_hash="f" * 64)
    result = ledger.claim(altered, now_unix=NOW)
    assert result.status == "request_id_conflict"
    assert result.authorizes_mutation is False


def test_expired_request_never_creates_database(tmp_path):
    path = tmp_path / "replay.db"
    request = _request()
    report = InspectionReplayLedger(path).claim(request, now_unix=NOW + 61)
    assert report.status == "expired"
    assert report.authorizes_mutation is False
    assert not path.exists()


def test_bad_manual_request_cannot_create_database(tmp_path):
    from dataclasses import replace
    path = tmp_path / "replay.db"
    bogus = replace(_request(), authorizes_mutation=True)
    with pytest.raises(ValueError):
        InspectionReplayLedger(path).claim(bogus, now_unix=NOW)
    assert not path.exists()


def test_existing_symlink_is_refused_without_external_modification(tmp_path):
    outside = tmp_path / "external.db"
    outside.write_text("PRIVATE", encoding="utf-8")
    link = tmp_path / "replay.db"
    link.symlink_to(outside)
    with pytest.raises(PermissionError, match="symlink"):
        InspectionReplayLedger(link).claim(_request(), now_unix=NOW)
    assert outside.read_text(encoding="utf-8") == "PRIVATE"


def test_hardlinked_or_group_writable_ledger_refused(tmp_path):
    path = tmp_path / "replay.db"
    ledger = InspectionReplayLedger(path)
    ledger.claim(_request(), now_unix=NOW)
    twin = tmp_path / "twin.db"
    os.link(path, twin)
    with pytest.raises(PermissionError):
        ledger.claim(_request("b" * 32), now_unix=NOW)
    assert twin.exists()
    twin.unlink()
    if os.name == "posix":
        os.chmod(path, 0o666)
        with pytest.raises(PermissionError):
            ledger.claim(_request("b" * 32), now_unix=NOW)


def test_group_writable_parent_rejected(tmp_path):
    if os.name != "posix":
        pytest.skip("Owner-only POSIX permissions")
    directory = tmp_path / "unsafe"
    directory.mkdir()
    os.chmod(directory, 0o777)
    ledger = InspectionReplayLedger(directory / "replay.db")
    with pytest.raises(PermissionError, match="parent"):
        ledger.claim(_request(), now_unix=NOW)
    assert not (directory / "replay.db").exists()


def test_database_corruption_does_not_silently_recreate_ledger(tmp_path):
    path = tmp_path / "replay.db"
    path.write_bytes(b"not a sqlite file")
    with pytest.raises(sqlite3.DatabaseError):
        InspectionReplayLedger(path).claim(_request(), now_unix=NOW)
    assert path.read_bytes() == b"not a sqlite file"


def test_same_request_from_concurrent_threads_is_recorded_once(tmp_path):
    ledger = InspectionReplayLedger(tmp_path / "replay.db")
    request = _request()
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(
            lambda _: ledger.claim(request, now_unix=NOW).status,
            range(16),
        ))
    assert statuses.count("recorded_for_inspection") == 1
    assert statuses.count("already_seen") == 15


def test_same_request_from_independent_processes_is_recorded_once(tmp_path):
    path = tmp_path / "replay.db"
    with ProcessPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(
            _claim_from_process,
            [(path, "a" * 32)] * 12,
        ))
    assert statuses.count("recorded_for_inspection") == 1
    assert statuses.count("already_seen") == 11


def test_different_request_ids_are_distinct(tmp_path):
    ledger = InspectionReplayLedger(tmp_path / "replay.db")
    assert ledger.claim(_request("a" * 32), now_unix=NOW).status == (
        "recorded_for_inspection"
    )
    assert ledger.claim(_request("b" * 32), now_unix=NOW).status == (
        "recorded_for_inspection"
    )
