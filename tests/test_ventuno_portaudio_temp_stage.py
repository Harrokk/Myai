"""Guard PortAudio compatibility staging without real apt or audio device."""
from pathlib import Path

import pytest

import scripts.ventuno_portaudio_temp_stage as pa


def test_missing_arch_is_no_go(tmp_path, monkeypatch):
    monkeypatch.setattr(pa, "run_bounded", lambda *a, **k:
                        pytest.fail("apt must not run on x86 host"))
    r = pa.stage_portaudio_for_import(
        tmp_path / "python", tmp_path / "myai-voice-portaudio", tmp_path,
        arm=False,
    )
    assert r["status"] == "no-go-distro-portaudio-staging"
    assert r["system_packages_installed"] is False


def test_package_path_size_and_arch_restrictions(tmp_path):
    candidate = tmp_path / "libportaudio2_19.6-1_arm64.deb"
    candidate.write_bytes(b"dummy")
    assert pa.valid_package(candidate, tmp_path)
    wrong = tmp_path / "libportaudio2_19.6-1_amd64.deb"
    wrong.write_bytes(b"dummy")
    assert not pa.valid_package(wrong, tmp_path)


def test_extracted_library_must_resolve_inside_temp(tmp_path):
    root = tmp_path / "extracted"
    libs = root / "usr" / "lib" / "aarch64-linux-gnu"
    libs.mkdir(parents=True)
    lib = libs / "libportaudio.so.2.0.0"
    lib.write_bytes(b"synthetic")
    (libs / "libportaudio.so.2").symlink_to(lib.name)
    assert pa.extracted_library(root) == lib.resolve()


def test_escape_symlink_is_rejected(tmp_path):
    root = tmp_path / "extracted"
    libs = root / "usr" / "lib" / "aarch64-linux-gnu"
    libs.mkdir(parents=True)
    outside = tmp_path / "not-in-package.so"
    outside.write_bytes(b"not permitted")
    (libs / "libportaudio.so.2").symlink_to(outside)
    assert pa.extracted_library(root) is None


def test_no_root_install_only_apt_download_dpkg_extract(monkeypatch, tmp_path):
    base = tmp_path / "runner"
    base.mkdir()
    stage = base / "myai-voice-portaudio"
    sandbox = base / "python"
    sandbox.write_bytes(b"python binary")
    monkeypatch.setattr(pa.shutil, "which", lambda p:
                        f"/usr/bin/{p}" if p in ("apt", "dpkg-deb") else None)
    calls = []

    def simulated(argv, **kwargs):
        calls.append(argv)
        assert kwargs["cwd"] in (base, stage)
        assert argv[0] not in ("sudo", "apt-get", "dpkg")
        assert "install" not in argv
        if argv[1:] == ["download", "libportaudio2"]:
            (stage / "libportaudio2_19.6_arm64.deb").write_bytes(b"package")
        if "--extract" in argv:
            out = Path(argv[-1])
            libdir = out / "usr" / "lib" / "aarch64-linux-gnu"
            libdir.mkdir(parents=True)
            (libdir / "libportaudio.so.2").write_bytes(b"verified")
        return {"success": True, "exit_code": 0}

    monkeypatch.setattr(pa, "run_bounded", simulated)
    result = pa.stage_portaudio_for_import(sandbox, stage, base, arm=True)
    assert result["status"] == "sounddevice-imports-with-temporary-portaudio"
    assert result["sounddevice_import_with_isolated_portaudio"] is True
    assert result["system_packages_installed"] is False
    assert result["audio_stream_opened"] is False
    assert len(calls) == 4
    assert calls[0][1:] == ["download", "libportaudio2"]
    assert calls[-1][1:3] == ["-I", "-c"]
    assert "import sounddevice" in calls[-1][-1]


def test_existing_temporary_folder_refused(tmp_path, monkeypatch):
    stage = tmp_path / "myai-voice-portaudio"
    stage.mkdir()
    sandbox = tmp_path / "python"
    sandbox.write_text("placeholder")
    monkeypatch.setattr(pa, "run_bounded", lambda *a, **k:
                        pytest.fail("must not overwrite temp content"))
    monkeypatch.setattr(pa.shutil, "which", lambda p: "/usr/bin/" + p)
    report = pa.stage_portaudio_for_import(
        sandbox, stage, tmp_path, arm=True,
    )
    assert report["status"] == "no-go-staging-tools-or-path"
