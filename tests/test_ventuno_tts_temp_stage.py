"""Test TTS distro package staging without network, install or playback."""
from pathlib import Path

import pytest

import scripts.ventuno_tts_temp_stage as stage


def test_stage_on_wrong_arch_never_fetches(tmp_path, monkeypatch):
    monkeypatch.setattr(stage, "run_command", lambda *args, **kwargs:
                        pytest.fail("no packages may download on x86"))
    out = stage.stage_sweden_tts(
        tmp_path / "myai-tts-espeak-stage", tmp_path, arm=False
    )
    assert out["status"] == "no-go-runner-temp-or-package-tool"
    assert out["services_changed"] is False


def test_deb_must_be_official_allowlisted_arm64_or_all(tmp_path):
    p = tmp_path / "espeak-ng_1.51-1_arm64.deb"
    p.write_bytes(b"synthetic")
    assert stage.safe_deb(p, tmp_path, "espeak-ng")
    assert not stage.safe_deb(p, tmp_path, "evil")
    q = tmp_path / "espeak-ng-data_1.51-1_all.deb"
    q.write_bytes(b"synthetic")
    assert stage.safe_deb(q, tmp_path, "espeak-ng-data")
    wrong = tmp_path / "espeak-ng_1.51-1_amd64.deb"
    wrong.write_bytes(b"synthetic")
    assert not stage.safe_deb(wrong, tmp_path, "espeak-ng")


def test_existing_stage_dir_is_not_overwritten(tmp_path, monkeypatch):
    target = tmp_path / "myai-tts-espeak-stage"
    target.mkdir()
    monkeypatch.setattr(stage, "run_command", lambda *a, **k:
                        pytest.fail("no execution"))
    assert stage.stage_sweden_tts(target, tmp_path, arm=True)["status"] == (
        "no-go-runner-temp-or-package-tool"
    )


def test_symlink_espeak_binary_rejected(tmp_path):
    root = tmp_path / "myai-tts-espeak-stage"
    bin_dir = root / "extracted/usr/bin"
    data_dir = root / "extracted/usr/share/espeak-ng-data"
    bin_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"no")
    try:
        (bin_dir / "espeak-ng").symlink_to(outside)
    except OSError:
        pytest.skip("no symlink support")
    assert stage.espeak_paths(root) == (None, None)


def test_no_apt_install_or_device_output(monkeypatch, tmp_path):
    import io
    import math
    import struct
    import wave

    wav_stream = io.BytesIO()
    samples = [int(2400 * math.sin(2 * math.pi * 220 * i / 22050))
               for i in range(22050)]
    with wave.open(wav_stream, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(22050)
        writer.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    sample_wav = wav_stream.getvalue()
    root = tmp_path / "myai-tts-espeak-stage"
    monkeypatch.setattr(stage.shutil, "which", lambda tool: "/usr/bin/" + tool)
    monkeypatch.setattr(stage.shutil, "disk_usage", lambda path:
                        __import__("types").SimpleNamespace(free=500 * 1024 * 1024))
    seen = []

    def fake(args, cwd, **kwargs):
        seen.append(args)
        assert "sudo" not in args and "install" not in args
        assert args[0] in ("/usr/bin/apt", "/usr/bin/dpkg-deb") or                args[0].endswith("/espeak-ng")
        if args[1:2] == ["download"]:
            name = args[2]
            ending = "all" if name == "espeak-ng-data" else "arm64"
            (root / (name + "_1.51-1_" + ending + ".deb")).write_bytes(b"pkg")
            return {"ok": True}
        if args[1:2] == ["--field"]:
            filename = args[2]
            return {"ok": True, "stdout":
                    b"all\n" if "espeak-ng-data" in filename else b"arm64\n"}
        if args[1:2] == ["--extract"]:
            ex = root / "extracted"
            executable = ex / "usr/bin/espeak-ng"
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_bytes(b"ELF")
            (ex / "usr/share/espeak-ng-data").mkdir(parents=True, exist_ok=True)
            return {"ok": True}
        if args[0].endswith("/espeak-ng"):
            assert "--stdout" in args
            assert "-v" in args and "sv" in args
            assert kwargs["timeout"] <= 8
            return {"ok": True, "stdout": sample_wav}
        return {"ok": True}

    monkeypatch.setattr(stage, "run_command", fake)
    report = stage.stage_sweden_tts(root, tmp_path, arm=True)
    assert report["status"] == "isolated-swedish-tts-signal-verified"
    assert report["swedish_pcm_synthesis_verified"] is True
    assert report["physical_playback_verified"] is False
    assert report["microphone_used"] is False
    assert report["system_packages_installed"] is False
    assert report["services_changed"] is False
    assert len([args for args in seen if args[1:2] == ["download"]]) == 3
    assert all("play" not in str(a) for a in seen)


def test_bounded_run_timeout_does_not_leak_stdout(monkeypatch, tmp_path):
    def timeout(*args, **kwargs):
        raise __import__("subprocess").TimeoutExpired(
            "espeak-ng", timeout=8, output=b"private speech"
        )
    monkeypatch.setattr(stage.subprocess, "run", timeout)
    report = stage.run_command(["espeak-ng"], tmp_path, timeout=8)
    assert report["reason"] == "timeout"
    assert "private" not in str(report)
