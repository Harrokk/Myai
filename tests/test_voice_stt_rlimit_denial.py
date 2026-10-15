"""Synthetic fail-closed worker startup tests; NEVER start FasterWhisper or audio.

Check that failure of Linux resource.setrlimit during worker bootstrap
happens BEFORE model import for both one-shot and persistent workers,
that no transcript appears, and that parent STT wrappers reap the child.
"""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from core.voice_stt_process import run_deadlined
from core.voice_stt_persistent import PersistentFasterWhisperSTT

CONFIG = {
    "model_name": "tiny", "device": "cpu", "compute_type": "int8",
    "language": "sv", "sample_rate": 16000,
    "channels": 1, "sample_width": 2,
}


def failing_worker_argv(tmp_path, mode, refused):
    """Launch actual checked-in worker.main() with synthetic denied rlimit.

    Inject refusal in a DISPOSABLE Python process, not in the parent.
    A trap records if native speech provider import was attempted.
    """
    root = str(Path(__file__).resolve().parents[1])
    sentinel = str(tmp_path / f"FORBIDDEN_NATIVE_IMPORT_{mode}_{refused}")
    module = (
        "core.voice_stt_worker"
        if mode == "oneshot" else "core.voice_stt_persistent_worker"
    )
    source = f"""
import builtins, json, os, resource, sys
sys.path.insert(0, {root!r})
orig_import = builtins.__import__
def trap_import(name, *args, **kwargs):
    if name == "modules.voice.providers":
        with open({sentinel!r}, "w") as marker:
            marker.write("NATIVE_MODEL_IMPORT_MUST_NOT_HAPPEN")
        raise AssertionError("Native STT import should never be reached")
    return orig_import(name, *args, **kwargs)
builtins.__import__ = trap_import
def denied(kind, requested):
    if kind == getattr(resource, {refused!r}):
        raise PermissionError("SECRET_DRIVER_PATH_OR_NATIVE_RESOURCE")
resource.setrlimit = denied
sys.argv = [{module!r}, json.dumps({CONFIG!r})]
from {module} import main
sys.exit(main())
"""
    return [sys.executable, "-I", "-u", "-c", source], Path(sentinel)


@pytest.mark.parametrize("mode", ["oneshot", "persistent"])
@pytest.mark.parametrize("denied", ["RLIMIT_CPU", "RLIMIT_AS"])
def test_real_child_rlimit_denial_returns_failure_without_model_import(
    tmp_path, mode, denied
):
    argv, sentinel = failing_worker_argv(tmp_path, mode, denied)
    from core.voice_stt_child_limits import add_limit_environment
    env = add_limit_environment(
        {"PATH": "/usr/bin:/bin", "HOME": "/tmp",
         "PYTHONDONTWRITEBYTECODE": "1"},
        cpu_seconds=5, virtual_memory_mib=1024,
    )
    child = subprocess.run(
        argv, input=b"SYNTHETIC_PRIVATE_AUDIO", env=env, cwd="/",
        capture_output=True, timeout=8, check=False,
    )
    assert child.returncode == 2
    assert child.stdout == b""
    assert b"SECRET" not in child.stderr
    assert b"PRIVATE_AUDIO" not in child.stderr
    assert not sentinel.exists()


@pytest.mark.parametrize("denied", ["RLIMIT_CPU", "RLIMIT_AS"])
def test_oneshot_parent_reaps_worker_rejected_during_resource_bootstrap(
    tmp_path, denied
):
    argv, sentinel = failing_worker_argv(tmp_path, "oneshot", denied)
    owned = []

    def launch(_argv, **kwargs):
        child = subprocess.Popen(argv, **kwargs)
        owned.append(child)
        return child

    with pytest.raises(RuntimeError, match="Isolated STT worker failed") as e:
        run_deadlined(
            ["IGNORED_SYNTHETIC_TEST_ARGV"],
            b"SYNTHETIC_PRIVATE_AUDIO", 5,
            popen=launch, cpu_seconds=5,
            virtual_memory_mib=1024,
        )
    assert "SECRET" not in str(e.value)
    assert "PRIVATE" not in str(e.value)
    assert len(owned) == 1
    assert owned[0].poll() == 2
    assert not sentinel.exists()


@pytest.mark.parametrize("denied", ["RLIMIT_CPU", "RLIMIT_AS"])
def test_persistent_parent_reaps_failed_bootstrap_before_next_request(
    tmp_path, denied
):
    argv, sentinel = failing_worker_argv(tmp_path, "persistent", denied)
    model = PersistentFasterWhisperSTT(
        **CONFIG, timeout_seconds=5, max_utterances=2,
        cpu_seconds=5, virtual_memory_mib=1024,
    )
    model._argv = argv  # Test-only replacement; production fixed worker.
    try:
        with pytest.raises(RuntimeError) as e:
            model.transcribe(b"SYNTHETIC_PRIVATE_AUDIO")
        assert "SECRET" not in str(e.value)
        assert "PRIVATE_AUDIO" not in str(e.value)
        assert model._worker is None
        assert model._cleanup_required is False
        assert model._count == 0
        assert not sentinel.exists()
    finally:
        model.close()
