"""Source release gates never permit installed MyAI or NPU activation."""
from pathlib import Path
from types import SimpleNamespace

from scripts import ventuno_source_release_readiness as mod


def pretend_git(success=True, is_dirty=False):
    def run(args, **kwargs):
        command = args[3]
        if command == "rev-parse":
            return SimpleNamespace(returncode=0, stdout="b" * 40 + "\n")
        if command == "status":
            return SimpleNamespace(returncode=0, stdout=" M core/assistant.py\n" if is_dirty else "")
        if command == "merge-base":
            return SimpleNamespace(returncode=0 if success else 1, stdout="")
        return SimpleNamespace(returncode=1, stdout="")
    return run


def test_software_candidate_never_deploys_or_authorizes_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "workflows", lambda _: {"status": "no-automatic-hardware-triggers-on-candidate"})
    monkeypatch.setattr(mod, "quarantine", lambda _: {"quarantine_verified": True})
    monkeypatch.setattr(mod, "stage", lambda *_: {"candidate_safe_by_contract": True})
    monkeypatch.setattr(mod, "wheel_lock", lambda _: {"source_lock_consistent": True})
    result = mod.inspect(tmp_path, runner=pretend_git())
    assert result["status"] == "source-candidate-consistent-but-not-deploy-authorized"
    assert result["main_reviewed_parent_ancestor"] is True
    assert result["draft_reviewed_parent_ancestor"] is True
    assert result["production_deploy_authorized"] is False
    assert result["hardware_stop_and_rollback_physically_verified"] is False


def test_source_commit_unknown_or_dirty_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "workflows", lambda _: {"status": "no-automatic-hardware-triggers-on-candidate"})
    monkeypatch.setattr(mod, "quarantine", lambda _: {"quarantine_verified": True})
    monkeypatch.setattr(mod, "stage", lambda *_: {"candidate_safe_by_contract": True})
    monkeypatch.setattr(mod, "wheel_lock", lambda _: {"source_lock_consistent": True})
    assert mod.inspect(tmp_path, runner=pretend_git(is_dirty=True))["status"] == "blocked-source-candidate"
    assert mod.inspect(tmp_path, runner=pretend_git(success=False))["status"] == "blocked-source-candidate"


def test_default_failed_release_never_reports_npu_or_audio_signoff():
    # Safe even when Git history was intentionally shallow.
    result = mod.inspect()
    assert result["installed_voice_native_abi_signed_off"] is False
    assert result["npu_htp_profiler_verified"] is False
    assert result["full_voice_model_inference_verified"] is False
    assert result["merge_to_main_authorized"] is False
