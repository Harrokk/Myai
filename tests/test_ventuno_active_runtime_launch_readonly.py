"""Active runtime provenance report is only a candidate, never proof of loaded config."""
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import ventuno_active_runtime_launch_readonly as mod


def test_source_only_does_not_read_runner_or_proc(monkeypatch):
    def forbidden(*_a, **_kw):
        raise AssertionError("systemctl called in source-only mode")
    monkeypatch.setattr(mod.subprocess, "run", forbidden)
    report = mod.inspect()
    assert report["status"] == "blocked-active-launch-or-code-unverified"
    assert report["effective_live_settings_attested"] is False
    assert report["hardware_test_authorized"] is False


def test_known_module_or_exact_script_shape_only():
    for seq in (
        ["/usr/bin/python3", "-m", "scripts.ventuno_runtime"],
        ["/home/arduino/MyAI/.venv/bin/python", "-B",
         "/home/arduino/MyAI/scripts/ventuno_runtime.py"],
    ):
        cmdline = "\0".join(seq).encode() + b"\0"
        assert mod._is_known_invocation(cmdline) is True
    for seq in (
        ["/usr/bin/python3", "-c", "exec('hidden')"],
        ["/usr/bin/python3", "-m", "other.service"],
        ["/usr/bin/python3", "-m", "scripts.ventuno_runtime", "--skip-preflight"],
        ["/home/arduino/MyAI/.venv/bin/python", "mail.py"],
    ):
        assert mod._is_known_invocation("\0".join(seq).encode() + b"\0") is False


def test_only_same_source_file_and_known_exact_argv_is_candidate():
    digest = b"x" * 32
    ok = b"/usr/bin/python3\0-m\0scripts.ventuno_runtime\0"
    assert mod.classify("731", ok, digest, digest)[
        "installed_runtime_source_matches_exact_checkout"
    ] is True
    unknown = mod.classify("731", ok, digest, b"y" * 32)
    assert unknown["status"] == "blocked-active-launch-or-code-unverified"
    assert unknown["effective_live_settings_attested"] is False


def test_real_proc_and_file_readings_mocked_without_emitting_args(tmp_path):
    root = tmp_path / "board"
    source = tmp_path / "source"
    for project in (root, source):
        script = project / "scripts" / "ventuno_runtime.py"
        script.parent.mkdir(parents=True)
        script.write_text("SAFE_EXPECTED_CHECKED_SOURCE")
    proc = tmp_path / "proc" / "12345"
    proc.mkdir(parents=True)
    proc.joinpath("cmdline").write_bytes(
        b"/usr/bin/python3\0-m\0scripts.ventuno_runtime\0"
    )
    report = mod.inspect(
        board=True, installed=root, source=source,
        proc_root=proc.parent,
        runner=lambda *_a, **_k: SimpleNamespace(stdout="12345\n",returncode=0),
    )
    assert report["service_main_pid_valid"] is True
    assert report["service_invocation_known"] is True
    assert report["effective_live_settings_attested"] is False
    serialized = json.dumps(report)
    assert "SAFE_EXPECTED" not in serialized
    assert "12345" not in serialized
    assert "/board/" not in serialized


def test_invalid_pid_fail_closed_before_procfs_access(tmp_path):
    root = tmp_path / "missing"
    report = mod.inspect(
        board=True, proc_root=root,
        runner=lambda *_a, **_k: SimpleNamespace(
            stdout="1234; PRIVATE_SECRET\n", returncode=0
        ),
    )
    assert report["service_main_pid_valid"] is False
    assert report["secrets_or_raw_argv_printed"] is False


def test_too_big_or_symlinked_installed_script_denied(tmp_path):
    data = tmp_path / "oversized.py"
    data.write_bytes(b"a" * (mod.MAX_SCRIPT_BYTES + 1))
    assert mod._file_digest(data) is None
    ref = tmp_path / "link.py"
    ref.symlink_to(data)
    assert mod._file_digest(ref) is None


def test_no_live_config_attestation_claim_even_when_source_matches():
    result = mod.classify(
        "17", b"/usr/bin/python3\0-m\0scripts.ventuno_runtime\0",
        b"a" * 32, b"a" * 32,
    )
    assert result["effective_live_settings_attested"] is False
    assert result["live_memory_settings_confirmed"] is False
    assert result["production_config_changed"] is False
