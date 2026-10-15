"""Host-only synthetic Linux rlimit tests; never load Whisper or touch live services."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from core.voice_stt_child_limits import (
    CPU_ENV, AS_ENV, MIB, add_limit_environment,
    apply_child_limits, validated_limits,
)


@pytest.mark.parametrize("patch", [
    (-1, 0), (1, 0), (4, 0), (301, 0),
    ("45", 0), (True, 0), (0.0, 0), (None, 0),
    (0, -1), (0, 500), (0, 1023), (0, 8193),
    (0, "2048"), (0, True), (0, 2048.0),
    (10 ** 400, 0), (0, 10 ** 400),
])
def test_invalid_resource_policy_is_rejected_before_worker_launch(patch):
    with pytest.raises(ValueError):
        validated_limits(*patch)
    with pytest.raises(ValueError):
        add_limit_environment({}, cpu_seconds=patch[0],
                              virtual_memory_mib=patch[1])


def test_default_policy_inherits_no_new_limits_and_no_secrets(monkeypatch):
    monkeypatch.setenv("HF_HUB_TOKEN", "SECRET_NEVER_EXPORT")
    clean = add_limit_environment({
        "PATH": "/usr/bin:/bin", "HF_HUB_OFFLINE": "1"
    })
    assert CPU_ENV not in clean and AS_ENV not in clean
    assert "HF_HUB_TOKEN" not in clean
    assert clean["HF_HUB_OFFLINE"] == "1"
    assert validated_limits() == (0, 0)


def test_child_only_env_cannot_weaken_inherited_limits():
    policy = add_limit_environment(
        {"PATH": "/usr/bin:/bin", CPU_ENV: "9999", AS_ENV: "1"},
        cpu_seconds=5, virtual_memory_mib=1024,
    )
    assert policy[CPU_ENV] == "5"
    assert policy[AS_ENV] == "1024"
    assert CPU_ENV not in add_limit_environment(policy)
    assert AS_ENV not in add_limit_environment(policy)


def _run_synthetic_child(cpu=0, mem=0, extra=None):
    # A fixed Python subprocess runs under its own independent process,
    # not an actual STT worker or VENTUNO audio/model backend.
    import resource
    root = str(Path(__file__).resolve().parents[1])
    code = (
        "import json,os,resource,sys,mmap;"
        f"sys.path.insert(0,{root!r});"
        "from core.voice_stt_child_limits import apply_child_limits;"
        "active=apply_child_limits();"
        "cpu=resource.getrlimit(resource.RLIMIT_CPU)[0];"
        "address=resource.getrlimit(resource.RLIMIT_AS)[0];"
        "blocked=False;"
        "exec('try:\\n mmap.mmap(-1, 2*1024*1024*1024)\\n"
        "except (MemoryError,OSError):\\n blocked=True');"
        "print(json.dumps({'active':active,'cpu':cpu,"
        "'virtual':address,'over_2gb_blocked':blocked}))"
    )
    env = add_limit_environment(
        {"PATH": "/usr/bin:/bin", "HOME": "/tmp",
         "PYTHONDONTWRITEBYTECODE": "1"},
        cpu_seconds=cpu, virtual_memory_mib=mem,
    )
    if extra:
        env.update(extra)
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        env=env, cwd="/", capture_output=True,
        check=False, timeout=8,
    )
    return completed


def test_real_synthetic_child_receives_cpu_and_virtual_address_limits():
    import resource
    before = (resource.getrlimit(resource.RLIMIT_CPU),
              resource.getrlimit(resource.RLIMIT_AS))
    r = _run_synthetic_child(cpu=5, mem=1024)
    assert r.returncode == 0, "Synthetic child resource check failed"
    report = json.loads(r.stdout)
    assert report["active"] is True
    assert report["cpu"] == 5
    assert report["virtual"] == 1024 * MIB
    assert report["over_2gb_blocked"] is True
    # Absolutely no changes to limits of the test runner or GenieX.
    assert (resource.getrlimit(resource.RLIMIT_CPU),
            resource.getrlimit(resource.RLIMIT_AS)) == before


def test_untrusted_child_environment_policy_fails_closed(monkeypatch):
    monkeypatch.setenv(CPU_ENV, "true")
    with pytest.raises(ValueError, match="Invalid STT child resource policy"):
        apply_child_limits()
    monkeypatch.delenv(CPU_ENV)
    monkeypatch.setenv(AS_ENV, "-1")
    with pytest.raises(ValueError, match="Invalid STT child resource policy"):
        apply_child_limits()
