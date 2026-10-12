"""Fail-closed tests for temporary ARM64 voice-wheel staging, no real pip."""
from pathlib import Path

import pytest

import scripts.ventuno_voice_wheel_staging as voice


def test_ram_meminfo_parse_and_missing_value(tmp_path):
    p = tmp_path / "meminfo"
    p.write_text("MemTotal: 16384000 kB\nMemAvailable: 3800000 kB\n")
    assert voice.mem_available_kib(p) == 3_800_000
    p.write_text("MemTotal: 16384000 kB\n")
    assert voice.mem_available_kib(p) is None


def test_preflight_requires_minimum_ram_and_disk():
    available = voice.preflight(
        voice.MIN_AVAILABLE_KIB, voice.MIN_DISK_FREE_BYTES, on_arm=True
    )
    assert available["may_stage"] is True
    assert available["production_venv_changed"] is False
    assert available["whisper_model_downloaded"] is False
    assert available["microphone_opened"] is False
    for mem, disk, arm in (
        (None, voice.MIN_DISK_FREE_BYTES, True),
        (voice.MIN_AVAILABLE_KIB - 1, voice.MIN_DISK_FREE_BYTES, True),
        (voice.MIN_AVAILABLE_KIB, None, True),
        (voice.MIN_AVAILABLE_KIB, voice.MIN_DISK_FREE_BYTES - 1, True),
        (voice.MIN_AVAILABLE_KIB, voice.MIN_DISK_FREE_BYTES, False),
    ):
        assert voice.preflight(mem, disk, on_arm=arm)["may_stage"] is False


def test_reject_existing_stage_or_outside_runner(tmp_path):
    runner = tmp_path / "runner"
    runner.mkdir()
    target = runner / "myai-voice-staging"
    assert voice.fresh_staging_dir(target, runner) is True
    target.mkdir()
    assert voice.fresh_staging_dir(target, runner) is False
    assert voice.fresh_staging_dir(
        tmp_path / "myai-voice-staging", runner
    ) is False


def test_never_stage_from_wrong_arch(monkeypatch, tmp_path):
    monkeypatch.setattr(voice.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(voice, "mem_available_kib", lambda: 9_000_000)
    monkeypatch.setattr(voice, "disk_free_bytes", lambda _p: 99_000_000_000)
    monkeypatch.setattr(
        voice, "result_of_command",
        lambda *a, **k: pytest.fail("must not invoke python or pip"),
    )
    result = voice.stage_light_voice(tmp_path / "python", tmp_path / "stage", tmp_path)
    assert result["status"] == "no-go-voice-staging-resources-or-platform"
    assert result["light_wheels_installed"] is False


def test_never_stage_when_memory_is_constrained(monkeypatch, tmp_path):
    monkeypatch.setattr(voice.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(voice, "mem_available_kib", lambda: 300_000)
    monkeypatch.setattr(voice, "disk_free_bytes", lambda _p: 30_000_000_000)
    monkeypatch.setattr(
        voice, "result_of_command",
        lambda *a, **k: pytest.fail("must not invoke pip when RAM low"),
    )
    result = voice.stage_light_voice(tmp_path / "python", tmp_path / "stage", tmp_path)
    assert result["may_stage"] is False


def test_disposable_install_command_binary_wheels_only(monkeypatch, tmp_path):
    runner = tmp_path / "runner"
    runner.mkdir()
    python = tmp_path / "python3"
    python.write_bytes(b"dummy")
    python.chmod(0o700)
    stage = runner / "myai-voice-staging"
    monkeypatch.setattr(voice.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(voice, "mem_available_kib", lambda: 9_000_000)
    monkeypatch.setattr(voice, "disk_free_bytes", lambda _p: 30_000_000_000)
    observed = []

    def fake_command(argv, **kwargs):
        observed.append((argv, kwargs))
        assert kwargs["cwd"] == runner
        assert kwargs["timeout"] <= 210
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        if argv[1:3] == ["-m", "venv"]:
            stage.mkdir()
            (stage / "bin").mkdir()
            (stage / "bin" / "python").write_bytes(b"fake")
        return {"completed": True, "exit_zero": True, "exit_code": 0}

    monkeypatch.setattr(voice, "result_of_command", fake_command)
    monkeypatch.setattr(voice, "import_probe", lambda *args: {
        "importable": True, "failure": None
    })
    out = voice.stage_light_voice(python, stage, runner)
    assert out["light_imports_verified"] is True
    assert len(observed) == 2
    installed = observed[1][0]
    assert "--only-binary=:all:" in installed
    assert "--no-cache-dir" in installed
    assert not any("faster-whisper" in arg for arg in installed)
    assert "--dry-run" not in installed
    assert "sounddevice>=0.5,<1" in installed
    assert out["geniex_changed"] is False


def test_optional_stt_wheel_resolution_dryrun_only(monkeypatch, tmp_path):
    runner = tmp_path / "runner"
    runner.mkdir()
    python = tmp_path / "python3"
    python.write_bytes(b"dummy")
    python.chmod(0o700)
    stage = runner / "myai-voice-staging"
    monkeypatch.setattr(voice.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(voice, "mem_available_kib", lambda: 9_000_000)
    monkeypatch.setattr(voice, "disk_free_bytes", lambda _p: 30_000_000_000)
    commands = []

    def fake(argv, **kwargs):
        commands.append(argv)
        if argv[1:3] == ["-m", "venv"]:
            stage.mkdir()
            (stage / "bin").mkdir()
            (stage / "bin" / "python").write_bytes(b"fake")
        return {"completed": True, "exit_zero": True, "exit_code": 0}

    monkeypatch.setattr(voice, "result_of_command", fake)
    monkeypatch.setattr(voice, "import_probe", lambda *args: {
        "importable": True, "failure": None
    })
    report = voice.stage_light_voice(python, stage, runner, check_stt_wheels=True)
    assert report["stt_wheel_resolution_verified"] is True
    assert len(commands) == 3
    assert "--dry-run" in commands[2]
    assert "--ignore-installed" in commands[2]
    assert "--only-binary=:all:" in commands[2]
    assert voice.STT_WHEELS[0] in commands[2]
    assert report["stt_model_loaded"] is False
    assert report["whisper_model_downloaded"] is False


def test_pip_diagnostics_never_return_text_or_credentials(monkeypatch):
    def fake_run(*a, **kw):
        return type("Completed", (), {
            "returncode": 7, "stdout": "token=secret",
            "stderr": "private/path"
        })()
    monkeypatch.setattr(voice.subprocess, "run", fake_run)
    report = voice.result_of_command(["python", "-m", "pip"], timeout=3)
    assert report == {"completed": True, "exit_zero": False, "exit_code": 7}
    assert "secret" not in str(report)


def test_import_probe_reports_only_error_category_and_library(monkeypatch, tmp_path):
    class Result:
        returncode = 1
        stderr = (
            "Traceback: /home/arduino/private/dir\n"
            "OSError: libportaudio.so.2: cannot open shared object file\n"
        )
        stdout = "secret_token=abcde"

    monkeypatch.setattr(voice.subprocess, "run", lambda *a, **kw: Result())
    report = voice.import_probe(
        tmp_path / "python", "sounddevice", tmp_path, {},
    )
    assert report["importable"] is False
    assert report["failure"] == "OSError"
    assert report["missing_library"] == "libportaudio.so.2"
    assert "private" not in str(report)
    assert "secret_token" not in str(report)


def test_import_probe_disallows_arbitrary_code(monkeypatch, tmp_path):
    monkeypatch.setattr(
        voice.subprocess, "run", lambda *a, **kw:
        pytest.fail("unsafe module requested")
    )
    with pytest.raises(ValueError, match="invalid-optional-module"):
        voice.import_probe(
            tmp_path / "python", "__import__('os').system('whoami')",
            tmp_path, {},
        )


def test_missing_portaudio_can_defer_only_sounddevice(monkeypatch, tmp_path):
    runner = tmp_path / "runner"
    runner.mkdir()
    base_python = tmp_path / "python3"
    base_python.write_bytes(b"base")
    base_python.chmod(0o700)
    stage = runner / "myai-voice-staging"
    monkeypatch.setattr(voice.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(voice, "mem_available_kib", lambda: 9_000_000)
    monkeypatch.setattr(voice, "disk_free_bytes", lambda _p: 30_000_000_000)

    def fake_cmd(args, **kwargs):
        if args[1:3] == ["-m", "venv"]:
            stage.mkdir()
            (stage / "bin").mkdir()
            (stage / "bin" / "python").write_bytes(b"fake")
        return {"completed": True, "exit_zero": True, "exit_code": 0}

    monkeypatch.setattr(voice, "result_of_command", fake_cmd)
    def fake_import(_p, name, _folder, _env):
        if name == "sounddevice":
            return {"importable": False, "failure": "OSError"}
        return {"importable": True, "failure": None}
    monkeypatch.setattr(voice, "import_probe", fake_import)
    report = voice.stage_light_voice(
        base_python, stage, runner, allow_missing_portaudio=True
    )
    assert report["status"] == "light-packages-require-optional-PortAudio-runtime"
    assert report["light_wheels_installed"] is True
    assert report["light_imports_verified"] is False
    assert report["module_imports"]["webrtcvad"]["importable"] is True
    assert report["module_imports"]["pyttsx3"]["importable"] is True
    assert report["production_venv_changed"] is False
