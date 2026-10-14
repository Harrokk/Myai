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
