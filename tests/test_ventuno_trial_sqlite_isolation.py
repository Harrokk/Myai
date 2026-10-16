"""Real SQLite transaction isolation using only temporary test directories."""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from core.assistant import MyAICore
from scripts.ventuno_trial_runtime_layout import inspect
from scripts.ventuno_isolated_voice_stage_contract import SOURCE, candidate


def trial_settings():
    return candidate(json.loads(SOURCE.read_text(encoding="utf-8")))


def test_disposable_trial_root_uses_only_disposable_sqlite_database(tmp_path):
    stage_root = tmp_path / "voice_stage"
    stage_root.mkdir()
    prod_root = tmp_path / "production"
    prod_root.mkdir()
    prod_db = prod_root / "memory.db"
    with sqlite3.connect(prod_db) as db:
        db.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        db.execute("INSERT INTO sentinel VALUES ('PRIVATE_PRODUCTION_SENTINEL')")
    original_bytes = prod_db.read_bytes()

    settings = trial_settings()
    assert inspect(settings, stage_root)["source_stage_file_boundary_trusted"]
    assert settings["memory"]["auto_save_enabled"] is False
    stage_db = stage_root / settings["memory"]["database"]
    stage_db.parent.mkdir(parents=True)
    llm = SimpleNamespace(provider_name="synthetic", model="fake-only", url="")
    assistant = MyAICore(settings, stage_root, tools={}, llm=llm)
    assistant.initialize()
    assert Path(assistant.memory.database_path) == stage_db
    assert stage_db.is_file()
    assistant.memory.save("synthetic", "synthetic content not user data")
    assert assistant.memory.contains("synthetic", "synthetic content not user data")
    assert prod_db.read_bytes() == original_bytes
    assert list(prod_root.iterdir()) == [prod_db]


def test_stage_runtime_path_symlink_or_escaped_database_is_rejected(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    settings = trial_settings()
    runtime = stage / "runtime"
    external = tmp_path / "untrusted_outside"
    external.mkdir()
    runtime.symlink_to(external, target_is_directory=True)
    assert inspect(settings, stage)["source_stage_file_boundary_trusted"] is False
    runtime.unlink()
    bad = trial_settings()
    bad["memory"]["database"] = "../memory.db"
    assert inspect(bad, stage)["source_stage_file_boundary_trusted"] is False
    bad["memory"]["database"] = "/home/arduino/MyAI/memory.db"
    assert inspect(bad, stage)["source_stage_file_boundary_trusted"] is False


def test_stage_file_layout_inspection_has_no_side_effects(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    before = list(stage.iterdir())
    output = inspect(trial_settings(), stage)
    assert output["status"] == "source-stage-file-layout-guard-passed"
    assert output["sqlite_or_audio_file_created"] is False
    assert output["runtime_activation_authorized"] is False
    assert list(stage.iterdir()) == before
