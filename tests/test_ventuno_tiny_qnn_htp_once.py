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
