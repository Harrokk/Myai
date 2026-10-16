"""No microphone, no real model: isolated import probe fault contracts."""
import json
from types import SimpleNamespace

from scripts import ventuno_isolated_voice_native_probe as mod


def test_unisolated_prefix_denies_without_running_children(tmp_path):
    def forbidden(*_a, **_k):
        raise AssertionError("Must not import when outside isolated venv")
    result = mod.inspect(tmp_path, runner=forbidden, prefix_check=False)
    assert result["all_seven_imports_passed"] is False
    assert result["production_packages_modified"] is False
    assert result["real_audio_authorized"] is False


def test_fake_imports_all_pass_but_no_hardware_claims(tmp_path):
    argv = []
    def fake(args, **kwargs):
        argv.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="ISOLATED_NATIVE_IMPORT_OK\n")
    result = mod.inspect(
        tmp_path, runner=fake,
        metadata=lambda _: "2.0.0+cpu",
        prefix_check=True,
    )
    assert result["status"] == "isolated-native-imports-pass-no-audio"
    assert result["all_seven_imports_passed"] is True
    assert len(argv) == len(mod.MODULES) == 7
    assert all(kwargs["timeout"] == 12 and kwargs["env"]["HF_HUB_OFFLINE"] == "1" for _, kwargs in argv)
    assert result["physical_runtime_compatibility_proven"] is False
    assert result["model_weights_loaded"] is False
    assert result["npu_or_dsp_opened"] is False


def test_one_import_failure_blocks_without_leaking_failure_text(tmp_path):
    def failing(args, **_):
        if args[-1] == "faster_whisper":
            return SimpleNamespace(returncode=1, stdout="PRIVATE_AUDIO_TOKEN")
        return SimpleNamespace(returncode=0, stdout="ISOLATED_NATIVE_IMPORT_OK")
    result = mod.inspect(
        tmp_path, runner=failing, metadata=lambda _: "1.0",
        prefix_check=True,
    )
    assert result["status"] == "blocked-native-import-or-venv-isolation"
    assert result["per_module_import"]["faster_whisper"] is False
    assert "PRIVATE_AUDIO_TOKEN" not in json.dumps(result)


def test_missing_version_blocks_without_import_failing(tmp_path):
    result = mod.inspect(
        tmp_path,
        runner=lambda *_a, **_k: SimpleNamespace(returncode=0, stdout="ISOLATED_NATIVE_IMPORT_OK"),
        metadata=lambda name: None if name == "numpy" else "1.0",
        prefix_check=True,
    )
    assert result["all_seven_imports_passed"] is False
    assert result["installed_dist_versions"]["numpy"] is None


def test_subprocess_timeouts_are_categorized_without_exposing_errors(tmp_path):
    import subprocess
    def timed_out(*_a, **_k):
        raise subprocess.TimeoutExpired("PRIVATE_AUDIO_SCRIPT", 12)
    result = mod.inspect(
        tmp_path, runner=timed_out, metadata=lambda _: "1.0",
        prefix_check=True,
    )
    assert result["all_seven_imports_passed"] is False
    assert "PRIVATE_AUDIO" not in json.dumps(result)
    assert result["microphone_opened"] is False


def test_source_only_script_requires_exactly_explicit_scratch_path():
    import pytest
    with pytest.raises(SystemExit):
        mod.main([])


def test_native_portaudio_error_reports_fixed_category_and_no_raw_detail(tmp_path):
    def fake(args, **_):
        if args[-1] == "sounddevice":
            return SimpleNamespace(returncode=47, stdout="MISSING_PORTAUDIO_LIBRARY\n")
        return SimpleNamespace(returncode=0, stdout="ISOLATED_NATIVE_IMPORT_OK\n")
    result = mod.inspect(
        tmp_path, runner=fake,
        metadata=lambda _: "1.0",
        prefix_check=True,
    )
    assert result["per_module_failure_category"]["sounddevice"] == (
        "missing-portaudio-shared-library"
    )
    assert result["all_seven_imports_passed"] is False
    assert result["real_audio_authorized"] is False



def test_bounded_native_child_source_is_syntactically_valid_without_imports():
    # Compile only; this does NOT load a native library or contact a device.
    compile(mod.CHILD, "<synthetic-native-import-child>", "exec")



def test_staged_private_portaudio_enables_only_isolated_child_loader(tmp_path):
    private_lib = tmp_path / "portaudio" / "lib"
    private_lib.mkdir(parents=True)
    (private_lib / "libportaudio.so.2").write_bytes(bytes.fromhex("7f454c46") + b"test-ELF-placeholder")
    checks = []
    def runner(args, **kwargs):
        if args[-1] == "USE_PRIVATE_PORTAUDIO":
            assert args[-2] == "sounddevice"
            assert kwargs["env"]["LD_LIBRARY_PATH"] == str(private_lib)
        checks.append(args[-1])
        return SimpleNamespace(returncode=0, stdout="ISOLATED_NATIVE_IMPORT_OK\n")
    report = mod.inspect(
        tmp_path, portaudio_directory=private_lib, runner=runner,
        metadata=lambda _: "1.0", prefix_check=True,
    )
    assert report["all_seven_imports_passed"] is True
    assert report["isolated_staged_portaudio_library_used"] is True
    assert report["portaudio_installed_in_production"] is False
    assert report["physical_runtime_compatibility_proven"] is False
    assert "USE_PRIVATE_PORTAUDIO" in checks


def test_staged_portaudio_cannot_use_symlink_or_outside_staging_root(tmp_path):
    import pytest
    staging = tmp_path / "stage"
    staging.mkdir()
    outside = tmp_path / "external"
    outside.mkdir()
    (outside / "libportaudio.so.2").write_bytes(bytes.fromhex("7f454c46") + b"something")
    assert mod._private_portaudio_dir(staging, outside) is None
    symlink = staging / "escapes"
    symlink.symlink_to(outside, target_is_directory=True)
    assert mod._private_portaudio_dir(staging, symlink) is None
