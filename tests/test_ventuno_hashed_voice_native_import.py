"""Verify isolated import gate with fake native loaders only."""
from scripts import ventuno_hashed_voice_native_import as gate


def test_empty_or_wrong_location_denied(tmp_path):
    temp = tmp_path / "tmp"
    temp.mkdir()
    root = temp / "myai-native-voice-abc123"
    root.mkdir()
    venv = root / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin/python").write_text("fake executable")
    kw = dict(
        stage_root=root, runner_temp=temp, interpreter_prefix=venv,
        arm64=True, marker="disposable-import-only",
    )
    assert gate.permitted(**kw) is True
    assert gate.permitted(**(kw | {"marker": "actual-recording"})) is False
    assert gate.permitted(**(kw | {"arm64": False})) is False
    assert gate.permitted(**(kw | {"interpreter_prefix": tmp_path})) is False
    assert gate.permitted(**(kw | {"stage_root": tmp_path})) is False


def test_symlink_stage_rejected(tmp_path):
    temp = tmp_path / "temp"
    temp.mkdir()
    target = temp / "different"
    target.mkdir()
    fake = temp / "myai-native-voice-link"
    fake.symlink_to(target, target_is_directory=True)
    assert gate.permitted(
        stage_root=fake, runner_temp=temp,
        interpreter_prefix=target / "venv",
        arm64=True, marker="disposable-import-only",
    ) is False


def test_import_success_does_not_claim_model_or_hardware():
    seen = []
    result = gate.import_report(loader=lambda name: seen.append(name))
    assert seen == list(gate.MODULES)
    assert result["all_imports_ok"] is True
    assert result["status"] == "isolated-native-package-imports-confirmed"
    for key in ("model_loaded", "microphone_opened", "tts_engine_initialized",
                "speaker_opened", "geniex_accessed", "npu_inference_performed",
                "production_venv_modified", "abi_full_end_to_end_approved"):
        assert result[key] is False


def test_import_errors_are_sanitized_and_not_successful():
    def loader(name):
        if name == "av":
            raise OSError("/PRIVATE/SECRET/libav.so missing SECRET_TOKEN")
        if name == "sounddevice":
            raise ModuleNotFoundError("MYAI_API_KEY_private")
    report = gate.import_report(loader)
    assert report["results"]["av"] == "OSError"
    assert report["results"]["sounddevice"] == "ModuleNotFoundError"
    assert report["all_imports_ok"] is False
    assert "SECRET_TOKEN" not in str(report)
    assert "MYAI_API_KEY_private" not in str(report)


def test_default_cli_never_attempts_native_import(monkeypatch, capsys):
    def denied(_):
        raise AssertionError("unsafe import")
    monkeypatch.setattr(gate.importlib, "import_module", denied)
    assert gate.main([]) == 2
    output = capsys.readouterr().out
    assert "blocked-unverified-stage-path" in output
