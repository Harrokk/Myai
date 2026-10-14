"""Guardrails for tiny QNN HTP attempt: pytest NEVER executes QNN models."""
import os
from pathlib import Path

from scripts import ventuno_tiny_qnn_htp_once as module


def test_denies_without_explicit_authorization(monkeypatch):
    monkeypatch.delenv("MYAI_ALLOW_ONE_TINY_QNN_HTP_ATTEMPT", raising=False)
    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(module, "available_memory_kib", lambda: 11 * 1048576)
    monkeypatch.setattr(module, "summarize_service", lambda *args: {})
    result = module.run_once()
    assert result["status"] == "no_go_not_authorized"
    assert result["htp_attempted"] is False


def test_denies_on_insufficient_memory_without_launching(monkeypatch):
    monkeypatch.setenv("MYAI_ALLOW_ONE_TINY_QNN_HTP_ATTEMPT", "yes")
    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(module, "available_memory_kib", lambda: 1)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k:
                        (_ for _ in ()).throw(AssertionError("launched qnn")))
    assert module.run_once()["status"] == "no_go_insufficient_ram"


def test_refuses_concurrent_existing_geniex_htp_session(monkeypatch):
    monkeypatch.setenv("MYAI_ALLOW_ONE_TINY_QNN_HTP_ATTEMPT", "yes")
    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(module, "available_memory_kib", lambda: 12 * 1048576)
    monkeypatch.setattr(module, "main_pid_from_systemd", lambda: 999)
    monkeypatch.setattr(module, "summarize_service", lambda *args: {
        "fast_rpc_secure_fd_open": True,
    })
    result = module.run_once()
    assert result["status"] == "no_go_existing_geniex_fastrpc_busy"
    assert result["htp_attempted"] is False


def test_native_output_requires_one_exact_nonzero_64_byte_result(tmp_path):
    target = tmp_path / "results" / "Result_0"
    target.mkdir(parents=True)
    assert module._output_summary(tmp_path) == "no_bounded_native_result"
    (target / "data.raw").write_bytes(b"\x00" * 64)
    assert module._output_summary(tmp_path) == "all_zero_output"
    (target / "data.raw").write_bytes(b"\x01" * 64)
    assert module._output_summary(tmp_path) == "native_64_byte_result_nonempty"
    (target / "extra.raw").write_bytes(b"\x01" * 64)
    assert module._output_summary(tmp_path) == "no_bounded_native_result"


def test_no_qnn_cli_flag_confidence_from_malformed_help(monkeypatch):
    class MockResult:
        returncode = 1
        stdout = "--model --backend --dlc_path"
        stderr = ""
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: MockResult())
    assert module._help_flags("qnn-net-run") == frozenset()


def test_private_error_capture_one_byte_lookahead_detects_truncation(tmp_path):
    # Only local synthetic files: never start QNN, FastRPC, or device services.
    (tmp_path / "stdout.private").write_bytes(b"x" * 16384 + b"permission denied SECRET")
    (tmp_path / "stderr.private").write_bytes(b"")
    report = module._classify_private_capture(tmp_path)
    assert report["output_capture_read_was_truncated"] is True
    assert report["stdout_sampled_bytes"] == 16384
    assert report["categories"] == ["unclassified"]
    assert "SECRET" not in str(report)
    assert "permission denied" not in str(report)


def test_private_error_capture_exact_limit_is_not_truncated(tmp_path):
    (tmp_path / "stdout.private").write_bytes(b"x" * 16384)
    (tmp_path / "stderr.private").write_bytes(b"backend create error")
    report = module._classify_private_capture(tmp_path)
    assert report["output_capture_read_was_truncated"] is False
    assert report["stdout_sampled_bytes"] == 16384
    assert report["categories"] == ["backend_initialization_failure"]
    assert "backend create error" not in str(report)


def test_htp_skel_locator_uses_only_packaged_hexagon_file(monkeypatch):
    expected = {
        "path_inside_usr": True,
        "file_regular": True,
        "header_class": "hexagon_elf_header",
        "package_owner": "qairt-dsp-binaries",
        "library_file_header_read": True,
    }
    called = []
    def fake_inspect(path, root):
        called.append((str(path), str(root)))
        return expected
    monkeypatch.setattr(module, "inspect_resolved_skel", fake_inspect)
    assert str(module._find_v75_skel_directory()) == "/usr/lib/dsp/cdsp"
    assert called == [
        ("/usr/lib/dsp/cdsp/libQnnHtpV75Skel.so", "/usr"),
    ]


def test_htp_skel_locator_fails_closed_on_untrusted_candidate(monkeypatch):
    valid = {
        "path_inside_usr": True,
        "file_regular": True,
        "header_class": "hexagon_elf_header",
        "package_owner": "qairt-dsp-binaries",
        "library_file_header_read": True,
    }
    for key, wrong in (
        ("path_inside_usr", False),
        ("file_regular", False),
        ("header_class", "aarch64_elf_header"),
        ("header_class", "unavailable"),
        ("package_owner", "unverified"),
        ("package_owner", "different_or_qualified_package"),
        ("library_file_header_read", False),
    ):
        suspect = {**valid, key: wrong}
        monkeypatch.setattr(
            module, "inspect_resolved_skel", lambda *args, v=suspect: v
        )
        assert module._find_v75_skel_directory() is None


def test_v75_gate_never_uses_other_fallback_directories(monkeypatch):
    monkeypatch.setattr(module, "inspect_resolved_skel", lambda *_: {
        "path_inside_usr": False, "file_regular": False,
        "header_class": "unavailable", "package_owner": "unverified",
        "library_file_header_read": False,
    })
    # If canonical QAIRT file is untrusted, do not search /opt, home,
    # /vendor or older alternate copies: return no-go.
    assert module._find_v75_skel_directory() is None
