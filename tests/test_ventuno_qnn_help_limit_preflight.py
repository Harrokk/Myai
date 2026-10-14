"""Unit tests for vendor --help startup comparison; never invoke vendor tool."""
from scripts import ventuno_qnn_help_limit_preflight as module


def test_classifies_success_and_never_collects_output(monkeypatch, tmp_path):
    calls = []
    class Completed:
        returncode = 0
    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return Completed()
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module.classify_help(
        "/usr/bin/qnn-net-run", {"HOME": str(tmp_path)},
        str(tmp_path), restrict=True,
    )
    assert result["result"] == "exit_zero"
    assert calls[0][0] == ["/usr/bin/qnn-net-run", "--help"]
    assert calls[0][1]["stdin"] == module.subprocess.DEVNULL
    assert calls[0][1]["stdout"] == module.subprocess.DEVNULL
    assert calls[0][1]["stderr"] == module.subprocess.DEVNULL
    assert calls[0][1]["preexec_fn"] is module._child_limits


def test_nonzero_and_launch_failure_are_not_reported_as_inference(monkeypatch, tmp_path):
    class Completed:
        returncode = 2
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: Completed())
    assert module.classify_help("qnn-net-run", {}, str(tmp_path), restrict=False)["result"] == "exit_nonzero"

    def unavailable(*a, **kw):
        raise FileNotFoundError("no program")
    monkeypatch.setattr(module.subprocess, "run", unavailable)
    assert module.classify_help("qnn-net-run", {}, str(tmp_path), restrict=False)["result"] == "launch_error"


def test_missing_qnn_or_dsp_refuses_all_invocation(monkeypatch):
    monkeypatch.setattr(module.shutil, "which", lambda _: None)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k:
                        (_ for _ in ()).throw(AssertionError("exec")))
    assert module.inspect_help_limits()["status"] == "no_go_required_files_not_found"
