"""Regression tests: read-only GenieX process association; no service calls."""
import json
from pathlib import Path

from scripts.ventuno_geniex_runtime_attestation import (
    classify_maps, is_geniex_process, parse_main_pid,
    process_evidence, service_tree, summarize_service,
)


def create_proc(tmp_path: Path, pid: int, name: str = "geniex", children=""):
    proc = tmp_path / str(pid)
    (proc / "task" / str(pid)).mkdir(parents=True)
    (proc / "fd").mkdir()
    (proc / "comm").write_text(name + "\n")
    (proc / "task" / str(pid) / "children").write_text(children)
    (proc / "exe").symlink_to("/usr/local/bin/" + name)
    (proc / "maps").write_text(
        "0000-0100 r--p 0 00:00 0 /home/user/private/libQnnHtp.so\n"
        "0100-0200 r--p 0 00:00 0 /usr/lib/libQnnSystem.so\n"
        "0200-0300 r--p 0 00:00 0 /home/secret/private-model.bin\n"
    )
    return proc


def test_mainpid_strict_acceptance():
    assert parse_main_pid("123\n") == 123
    for bad in ("0", "1", "-1", "", "123 456", "2\nTOKEN", "999999999999999"):
        assert parse_main_pid(bad) is None


def test_process_tree_never_scans_unrelated_pid(tmp_path):
    create_proc(tmp_path, 111, name="systemd", children="222")
    create_proc(tmp_path, 222, name="geniex", children="")
    create_proc(tmp_path, 333, name="geniex", children="")
    assert service_tree(tmp_path, 111) == [111, 222]
    assert is_geniex_process(tmp_path, 333)


def test_mapped_library_requires_exact_basename():
    text = ("abc /path/fakelibQnnHtp.so\n"
            "def /foo/libQnnHtp.so\n"
            "ghi /bar/libQnnSystem.so\n")
    mapped = classify_maps(text)
    assert mapped["libQnnHtp.so"] is True
    assert mapped["libQnnSystem.so"] is True
    assert mapped["libQnnHtpV75Stub.so"] is False


def test_backend_evidence_requires_qnn_and_secure_device(tmp_path):
    proc = create_proc(tmp_path, 55)
    (proc / "fd" / "7").symlink_to("/dev/fastrpc-cdsp-secure")
    r = summarize_service(tmp_path, 55)
    assert r["status"] == "backend-associated-with-service"
    assert r["runtime_backend_evidence"] is True
    assert r["geniex_process_count"] == 1
    assert r["actual_context_order_proven"] is False
    assert r["direct_htp_profiling_verified"] is False
    assert r["service_changes_allowed"] is False


def test_no_fast_rpc_device_is_inconclusive(tmp_path):
    create_proc(tmp_path, 42)
    r = summarize_service(tmp_path, 42)
    assert r["runtime_backend_evidence"] is False
    assert r["status"] == "inconclusive-backend-association"


def test_no_service_or_child_is_inconclusive(tmp_path):
    assert summarize_service(tmp_path, None)["status"] == "inconclusive-no-mainpid"
    create_proc(tmp_path, 101, name="bash")
    assert summarize_service(tmp_path, 101)["status"] == "inconclusive-no-geniex-child"


def test_sanitized_report_never_contains_proc_paths_or_secrets(tmp_path):
    proc = create_proc(tmp_path, 123)
    (proc / "fd" / "9").symlink_to("/dev/fastrpc-cdsp-secure")
    report = json.dumps(summarize_service(tmp_path, 123))
    assert "private-model" not in report
    assert "home/user" not in report
    assert str(tmp_path) not in report
    assert "cmdline" not in report
    assert "environ" not in report


def test_unreadable_maps_is_no_proof(tmp_path):
    proc = create_proc(tmp_path, 99)
    (proc / "maps").unlink()
    (proc / "fd" / "6").symlink_to("/dev/fastrpc-cdsp-secure")
    r = summarize_service(tmp_path, 99)
    assert r["complete_process_maps"] is False
    assert r["runtime_backend_evidence"] is False


def test_irrelevant_descriptor_cannot_claim_fast_rpc(tmp_path):
    proc = create_proc(tmp_path, 18)
    (proc / "fd" / "2").symlink_to("/dev/fastrpc-other")
    assert process_evidence(tmp_path, 18)["fast_rpc_secure_fd_open"] is False


def test_parent_wrapper_child_backend(tmp_path):
    create_proc(tmp_path, 66, name="bash", children="67")
    child = create_proc(tmp_path, 67, name="geniex")
    (child / "fd" / "8").symlink_to("/dev/fastrpc-cdsp-secure")
    r = summarize_service(tmp_path, 66)
    assert r["service_mainpid_present"] is True
    assert r["geniex_process_count"] == 1
    assert r["runtime_backend_evidence"] is True



def test_complete_fd_scan_is_reported_separately_from_no_open_fastrpc(
        tmp_path):
    create_proc(tmp_path, 300)
    r = summarize_service(tmp_path, 300)
    assert r["fast_rpc_secure_fd_open"] is False
    assert r["complete_fast_rpc_fd_scan"] is True
    assert r["complete_process_maps"] is True


def test_missing_fd_directory_never_implies_complete_scan(tmp_path):
    proc = create_proc(tmp_path, 301)
    (proc / "fd").rmdir()
    r = summarize_service(tmp_path, 301)
    assert r["fast_rpc_secure_fd_open"] is False
    assert r["complete_fast_rpc_fd_scan"] is False


def test_unreadable_descriptor_link_invalidates_absence_claim(
        tmp_path, monkeypatch):
    import os
    proc = create_proc(tmp_path, 302)
    (proc / "fd" / "6").symlink_to("/dev/fastrpc-unrelated")
    original = os.readlink

    def intermittent_readlink(path, *args, **kwargs):
        if str(path).endswith("/fd/6"):
            raise OSError("a simulated disappearing descriptor SECRET")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(os, "readlink", intermittent_readlink)
    r = summarize_service(tmp_path, 302)
    assert r["fast_rpc_secure_fd_open"] is False
    assert r["complete_fast_rpc_fd_scan"] is False
    assert "SECRET" not in json.dumps(r)


def test_capped_descriptor_scan_does_not_prove_no_fastrpc(tmp_path):
    from scripts import ventuno_geniex_runtime_attestation as module
    proc = create_proc(tmp_path, 303)
    for index in range(module.MAX_FDS + 1):
        (proc / "fd" / str(index)).symlink_to("/dev/other")
    r = summarize_service(tmp_path, 303)
    assert r["fast_rpc_secure_fd_open"] is False
    assert r["complete_fast_rpc_fd_scan"] is False
    assert module.process_evidence(tmp_path, 303)["fd_scan_capped"] is True


def test_no_main_pid_has_no_complete_fd_scan_evidence(tmp_path):
    r = summarize_service(tmp_path, None)
    assert r["complete_fast_rpc_fd_scan"] is False
    assert r["service_mainpid_present"] is False
