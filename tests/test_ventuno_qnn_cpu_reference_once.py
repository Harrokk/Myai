"""No-vendor tests for one controlled synthetic QNN CPU comparison."""
from scripts import ventuno_qnn_cpu_reference_once as module


def test_explicit_flag_required_before_any_vendor_binary_can_run(monkeypatch):
    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    monkeypatch.delenv("MYAI_ALLOW_ONE_TINY_QNN_CPU_ATTEMPT", raising=False)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k:
                        (_ for _ in ()).throw(AssertionError("unexpected binary")))
    result = module.cpu_once()
    assert result["status"] == "no_go_without_explicit_authorization"
    assert result["cpu_backend_exec_attempted"] is False
    assert result["htp_npu_inference_attempted"] is False


def test_requires_memory_headroom_before_cpu_call(monkeypatch):
    monkeypatch.setattr(module.platform, "machine", lambda: "aarch64")
    monkeypatch.setenv("MYAI_ALLOW_ONE_TINY_QNN_CPU_ATTEMPT", "yes")
    monkeypatch.setattr(module, "available_memory_kib", lambda: 100)
    result = module.cpu_once()
    assert result["status"] == "no_go_insufficient_memory"
    assert result["cpu_backend_exec_attempted"] is False


def test_cpu_only_child_limits_are_small():
    import inspect
    src = inspect.getsource(module.cpu_once)
    assert 'MYAI_ALLOW_ONE_TINY_QNN_CPU_ATTEMPT' in src
    assert '"libQnnCpu.so"' in inspect.getsource(module.locate_cpu_backend)
    assert 'libQnnHtp.so' not in src



def test_cpu_backend_picks_exact_verified_packaged_aarch64_file(monkeypatch):
    observed = []
    def inspect(path, root):
        observed.append((str(path), str(root)))
        return {
            "path_inside_usr": True,
            "file_regular": True,
            "header_class": "aarch64_elf_header",
            "package_owner": "qairt-libs",
            "library_file_header_read": True,
        }
    monkeypatch.setattr(module, "inspect_resolved_skel", inspect)
    assert str(module.locate_cpu_backend()) == "/usr/lib/libQnnCpu.so"
    assert observed == [("/usr/lib/libQnnCpu.so", "/usr")]


def test_cpu_backend_fails_closed_for_unverified_library(monkeypatch):
    trusted = {
        "path_inside_usr": True,
        "file_regular": True,
        "header_class": "aarch64_elf_header",
        "package_owner": "qairt-libs",
        "library_file_header_read": True,
    }
    for key, wrong in (
        ("path_inside_usr", False),
        ("file_regular", False),
        ("header_class", "hexagon_elf_header"),
        ("header_class", "not_elf_or_incomplete"),
        ("package_owner", "unverified"),
        ("package_owner", "qairt-dsp-binaries"),
        ("library_file_header_read", False),
    ):
        monkeypatch.setattr(module, "inspect_resolved_skel",
                            lambda *_args, v={**trusted, key: wrong}: v)
        assert module.locate_cpu_backend() is None


def test_cpu_result_uses_bounded_shared_attestor_not_legacy_glob():
    import inspect
    src = inspect.getsource(module.cpu_once)
    assert "attest_native_output(folder)" in src
    assert "_output_summary(folder)" not in src
    assert 'glob("*.raw")' not in src
    assert "raw_output_matches_previously_verified_x86_cpu" in src


def test_shared_reference_digest_identical_to_earlier_cpu_run():
    from scripts.ventuno_qnn_native_result_attestation import (
        EXPECTED_X86_CPU_RAW_SHA as attested_digest,
    )
    assert module.EXPECTED_X86_CPU_RAW_SHA == attested_digest
