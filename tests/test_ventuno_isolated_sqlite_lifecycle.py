"""Actual SQLite memory lifecycle in a *disposable* trial directory.

No production memory path is opened, copied, migrated or deleted.
No audio, model, tools or NPU activity is involved.
"""
import sqlite3
import tempfile
from pathlib import Path

from core.memory import MemoryStore
from scripts.ventuno_isolated_voice_stage_contract import STAGING_MEMORY


def test_private_sqlite_file_and_wal_never_escape_disposable_trial(tmp_path):
    production_sentinel = tmp_path / "memory.db"
    production_sentinel.write_bytes(b"PRODUCTION_SENTINEL_DO_NOT_TOUCH")
    sandbox_parent = tmp_path / "staging"
    sandbox_parent.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix="voice-", dir=sandbox_parent) as name:
        sandbox = Path(name)
        private_db = sandbox / STAGING_MEMORY
        private_db.parent.mkdir(parents=True)
        store = MemoryStore(private_db)
        store.init()
        # This synthetic test exercises optional explicit store writes only;
        # the actual staged voice profile has auto_save_enabled=False.
        store.save("synthetic", "NON_PRIVATE_TEST_SENTENCE")
        assert store.contains("synthetic", "NON_PRIVATE_TEST_SENTENCE") is True
        with sqlite3.connect(private_db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        assert count == 1
        assert private_db.is_relative_to(sandbox)
        assert production_sentinel.read_bytes() == b"PRODUCTION_SENTINEL_DO_NOT_TOUCH"
        assert not (tmp_path / "memory.db-wal").exists()
        assert not (tmp_path / "memory.db-shm").exists()
    assert not sandbox.exists()
    assert production_sentinel.read_bytes() == b"PRODUCTION_SENTINEL_DO_NOT_TOUCH"
    assert list(sandbox_parent.iterdir()) == []


def test_uninitialized_profile_never_creates_test_memory(tmp_path):
    from scripts.ventuno_isolated_voice_stage_contract import inspect, SOURCE, STAGE
    before = sorted(p.name for p in tmp_path.iterdir())
    assert inspect(SOURCE, STAGE)["candidate_safe_by_contract"] is True
    assert sorted(p.name for p in tmp_path.iterdir()) == before
