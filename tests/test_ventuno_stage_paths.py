"""Synthetic, no-network tests of fail-closed scratch staging roots."""
from pathlib import Path

from scripts import ventuno_stage_paths as guard
from scripts import ventuno_portaudio_temp_stage as portaudio
from scripts import ventuno_tts_temp_stage as tts


def test_scratch_root_rejects_installed_tree_and_ancestor(tmp_path):
    installed = tmp_path / "home" / "arduino" / "MyAI"
    installed.mkdir(parents=True)
    nested = installed / "voice"
    nested.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    assert guard.safe_scratch_root(scratch, production_root=installed)
    assert not guard.safe_scratch_root(installed, production_root=installed)
    assert not guard.safe_scratch_root(nested, production_root=installed)
    assert not guard.safe_scratch_root(installed.parent, production_root=installed)
    assert not guard.safe_scratch_root(tmp_path, production_root=installed)


def test_scratch_root_rejects_symlinks_and_missing_path(tmp_path):
    root = tmp_path / "real"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    assert not guard.safe_scratch_root(alias, production_root=tmp_path / "installed")
    assert not guard.safe_scratch_root(tmp_path / "absent",
                                       production_root=tmp_path / "installed")


def test_cli_rejects_missing_mismatched_and_aliased_stage(tmp_path):
    runner = tmp_path / "runner"
    runner.mkdir()
    stage = runner / "myai-native-voice-012345"
    stage.mkdir()
    accepted = {"RUNNER_TEMP": str(runner), "MYAI_STAGE_ROOT": str(stage)}
    assert guard.authorized_cli_stage(stage, accepted)
    assert not guard.authorized_cli_stage(stage, {})
    assert not guard.authorized_cli_stage(stage, {"RUNNER_TEMP": str(runner)})
    assert not guard.authorized_cli_stage(stage, {**accepted, "RUNNER_TEMP": str(stage)})
    assert not guard.authorized_cli_stage(stage, {**accepted, "MYAI_STAGE_ROOT": str(runner)})
    other = runner / "other-stage"
    other.mkdir()
    assert not guard.authorized_cli_stage(other, {**accepted, "MYAI_STAGE_ROOT": str(other)})
    alias = runner / "alias"
    alias.symlink_to(stage, target_is_directory=True)
    assert not guard.authorized_cli_stage(alias, accepted)


def test_portaudio_stage_denied_before_apt_when_root_unsafe(tmp_path, monkeypatch):
    runner = tmp_path / "runner"
    runner.mkdir()
    interpreter = runner / "python"
    interpreter.write_bytes(b"fake")
    monkeypatch.setattr(portaudio, "safe_scratch_root", lambda _: False)
    monkeypatch.setattr(portaudio.shutil, "which",
                        lambda _: (_ for _ in ()).throw(AssertionError("apt checked")))
    report = portaudio.stage_portaudio_for_import(
        interpreter, runner / "myai-voice-portaudio", runner, arm=True
    )
    assert report["status"] == "no-go-staging-tools-or-path"
    assert report["production_venv_changed"] is False


def test_tts_stage_denied_before_apt_when_root_unsafe(tmp_path, monkeypatch):
    runner = tmp_path / "runner"
    runner.mkdir()
    monkeypatch.setattr(tts, "safe_scratch_root", lambda _: False)
    monkeypatch.setattr(tts.shutil, "which",
                        lambda _: (_ for _ in ()).throw(AssertionError("apt checked")))
    report = tts.stage_sweden_tts(runner / "myai-tts-espeak-stage", runner, arm=True)
    assert report["status"] == "no-go-runner-temp-or-package-tool"
    assert report["system_packages_installed"] is False


def test_direct_cli_denied_without_matching_ci_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MYAI_STAGE_ROOT", raising=False)
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setattr(portaudio, "stage_portaudio_for_import",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("download attempted")))
    monkeypatch.setattr(tts, "stage_sweden_tts",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("synthesis attempted")))
    monkeypatch.setattr("sys.argv", ["portaudio", "--runner-temp", str(tmp_path),
                                     "--staged-python", str(tmp_path / "python")])
    assert portaudio.main() == 2
    monkeypatch.setattr("sys.argv", ["tts", "--runner-temp", str(tmp_path)])
    assert tts.main() == 2
    out = capsys.readouterr().out
    assert out.count("no-go-unverified-ci-stage") == 2
