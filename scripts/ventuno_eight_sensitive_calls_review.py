"""Audit the eight previously flagged sensitive AST call sites, source-only.

Does NOT execute any of the flagged sites. Coupled CI runs their
pre-existing isolated synthetic tests. No microphone, Whisper model,
HTP/NPU device, package install, or service control is permitted here.
"""
import ast
import json
from pathlib import Path


EXPECTED = {
    ("core/voice_stt_persistent.py", "_spawn", "subprocess.Popen"): "isolated-synthetic-worker-only",
    ("tests/test_ventuno_whisper_base_swedish_comparison.py",
     "_pure_phrase_metrics", "exec"): "fixed-checked-in-metric-source",
    ("tests/test_voice_process_census.py",
     "_synthetic_parent", "subprocess.Popen"): "disposable-synthetic-process-tree",
    ("tests/test_voice_process_census.py",
     "test_unrelated_synthetic_python_process_not_inaccurately_attributed",
     "subprocess.Popen"): "unrelated-disposable-process-negative-control",
    ("tests/test_voice_stt_process.py",
     "test_environment_is_forced_offline_and_does_not_inherit_secrets",
     "subprocess.Popen"): "offline-environment-fenced-child",
    ("tests/test_voice_stt_process.py",
     "test_one_shot_child_resource_env_is_child_only_and_default_off",
     "subprocess.Popen"): "isolated-child-resource-budget",
    ("tests/test_voice_stt_process_group.py",
     "_leader_with_helper", "subprocess.Popen"): "short-lived-synthetic-process-group",
    ("tests/test_voice_stt_rlimit_denial.py",
     "test_oneshot_parent_reaps_worker_rejected_during_resource_bootstrap",
     "subprocess.Popen"): "denied-worker-resource-bootstrap",
}
BANNED = {"eval", "exec", "pickle.loads", "marshal.loads",
          "os.system", "os.popen", "subprocess.Popen"}


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _dotted(node.value)
        return value + "." + node.attr if value else node.attr
    return ""


class _Collector(ast.NodeVisitor):
    def __init__(self):
        self.calls = []
        self.stack = []

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        call = _dotted(node.func)
        if call in BANNED:
            # The outermost function identifies the contextual trust boundary,
            # even if a nested closure contains the Popen.
            self.calls.append((
                self.stack[0] if self.stack else "<module>",
                call,
                node,
            ))
        self.generic_visit(node)


def inspect_source(root: Path):
    observed = []
    conditions = []
    for path in sorted({p for p, _, _ in EXPECTED}):
        file = root / path
        if file.is_symlink() or not file.is_file():
            return {"status": "fail-closed-source-file-unavailable",
                    "expected_sites": len(EXPECTED), "actual_sites": 0,
                    "unreviewed_sites": True, "prod_sites": 0,
                    "synthetic_test_sites": 0}
        try:
            tree = ast.parse(file.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, SyntaxError):
            return {"status": "fail-closed-source-unparseable",
                    "expected_sites": len(EXPECTED), "actual_sites": 0,
                    "unreviewed_sites": True, "prod_sites": 0,
                    "synthetic_test_sites": 0}
        collector = _Collector()
        collector.visit(tree)
        for function, call, node in collector.calls:
            observed.append((path, function, call))
            if (path, function, call) == (
                "core/voice_stt_persistent.py", "_spawn", "subprocess.Popen"
            ):
                # Inspect exact process isolation. A source change to
                # shell, environment, session, stdin/out or stderr must
                # invalidate the security review before any retest.
                keywords = {kw.arg: kw.value for kw in node.keywords}
                conditions.append(
                    "shell" not in keywords
                    and isinstance(keywords.get("start_new_session"), ast.Constant)
                    and keywords["start_new_session"].value is True
                    and isinstance(keywords.get("cwd"), ast.Constant)
                    and keywords["cwd"].value == "/"
                    and _dotted(keywords.get("stderr")) == "subprocess.DEVNULL"
                    and _dotted(keywords.get("stdin")) == "subprocess.PIPE"
                    and _dotted(keywords.get("stdout")) == "subprocess.PIPE"
                    and isinstance(keywords.get("env"), ast.Call)
                    and _dotted(keywords["env"].func) == "offline_environment"
                )
            if (path, function, call) == (
                "tests/test_ventuno_whisper_base_swedish_comparison.py",
                "_pure_phrase_metrics", "exec"
            ):
                conditions.append(
                    len(node.args) == 2
                    and _dotted(node.args[0]) == "compare._METRIC_SOURCE"
                    and _dotted(node.args[1]) == "namespace"
                )
    expected = sorted(EXPECTED)
    valid = sorted(observed) == expected and all(conditions) and len(conditions) == 2
    return {
        "status": ("eight-reviewed-synthetic-sites-catalogued"
                   if valid else "fail-closed-unreviewed-sensitive-call"),
        "expected_sites": len(expected),
        "actual_sites": len(observed),
        "unreviewed_sites": not valid,
        "prod_sites": sum(not path.startswith("tests/") for path, _, _ in observed),
        "synthetic_test_sites": sum(path.startswith("tests/") for path, _, _ in observed),
        "fixed_metric_source_required": True,
        "production_worker_offline_and_grouped_required": True,
        "live_model_launched": False,
        "microphone_or_speaker_opened": False,
        "htp_npu_attempted": False,
        "test_execution_performed_by_this_script": False,
    }


def main():
    result = inspect_source(Path(__file__).resolve().parent.parent)
    print("MYAI_EIGHT_SENSITIVE_CALLS_REVIEW_JSON=" +
          json.dumps(result, sort_keys=True))
    return 0 if not result["unreviewed_sites"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
