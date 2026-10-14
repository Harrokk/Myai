"""Static source-only repository audit. Never access real devices/services."""
from __future__ import annotations
import ast
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = {"memory.db", "memory.db-wal", "memory.db-shm"}
PRIVACY_FLAGS = [
    ("voice", "enabled"), ("voice", "tts_enabled"), ("voice", "handsfree_enabled"),
    ("camera", "enabled"), ("location", "enabled"),
    ("trusted_terminals", "auto_execute"), ("excel", "write_enabled"),
    ("ventuno", "rpc_write_enabled"), ("selfdev", "enabled"),
    ("selfdev", "promotion_enabled"),
]
RISKY_CALLS = {"eval", "exec", "pickle.loads", "marshal.loads", "os.system",
               "os.popen", "subprocess.Popen"}
def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted(node.value)
        return (parent + "." if parent else "") + node.attr
    return ""
def audit():
    paths_raw = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                               capture_output=True, check=True).stdout
    paths = [ROOT / x.decode("utf-8", "surrogateescape")
             for x in paths_raw.split(b"\0") if x]
    count = Counter()
    findings = []
    warnings = []
    for path in paths:
        name = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            findings.append({"type": "missing_tracked_file", "file": name})
            continue
        count["tracked_files"] += 1
        if path.name in FORBIDDEN or path.suffix in (".pyc", ".pyo", ".pyd"):
            findings.append({"type": "runtime_data_tracked", "file": name})
        if path.suffix == ".py":
            count["python_files"] += 1
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=name)
            except (SyntaxError, UnicodeError):
                findings.append({"type": "invalid_python", "file": name})
                continue
            count["python_syntax_valid"] += 1
            if name.startswith("tests/"):
                count["test_files"] += 1
                count["test_functions"] += sum(
                    isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name.startswith("test_") for n in ast.walk(tree))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                call = dotted(node.func)
                if call in RISKY_CALLS:
                    count["manual_review_sensitive_calls"] += 1
                    warnings.append({"type": "review_call", "file": name,
                                     "line": node.lineno, "call": call})
                if call.startswith("subprocess."):
                    if any(k.arg == "shell" and isinstance(k.value, ast.Constant)
                           and k.value.value is True for k in node.keywords):
                        warnings.append({"type": "shell_execution_review",
                                         "file": name, "line": node.lineno})
        if path.suffix == ".json":
            count["json_files"] += 1
            try:
                json.loads(path.read_text(encoding="utf-8-sig"))
                count["json_valid"] += 1
            except (ValueError, UnicodeError):
                findings.append({"type": "invalid_json", "file": name})
        if name.startswith(".github/workflows/") and path.suffix in (".yml", ".yaml"):
            count["workflow_files"] += 1
            source = path.read_text(encoding="utf-8-sig")
            if not re.search(r"(?m)^on:\s*$", source):
                findings.append({"type": "missing_workflow_on", "file": name})
            if not re.search(r"(?m)^permissions:\s*$", source):
                warnings.append({"type": "implicit_workflow_permissions", "file": name})
            if re.search(r"(?m)^\s*pull_request_target:\s*$", source):
                findings.append({"type": "privileged_pr_trigger", "file": name})
            if re.search(r"(?m)^\s*schedule:\s*$", source):
                warnings.append({"type": "scheduled_workflow", "file": name})
            if re.search(r"(?m)^\s*contents:\s*write\b", source):
                warnings.append({"type": "write_workflow_permission", "file": name})
            audio_markers = ("consent_to_record=True", "consent_to_play=True",
                             "--record-2s", "--consent-to-record")
            if any(mark in source for mark in audio_markers):
                count["audio_workflow_candidates"] += 1
                if "push:" in source and "github.event.head_commit.message" not in source:
                    warnings.append({"type": "audio_push_without_commit_guard",
                                     "file": name})
        if path.suffix in (".py", ".json", ".yml", ".yaml", ".sh"):
            try:
                source = path.read_text(encoding="utf-8-sig")
                if re.search(r"(?m)^(<{7}|={7}|>{7})\s", source):
                    findings.append({"type": "merge_conflict_marker", "file": name})
            except (UnicodeError, OSError):
                findings.append({"type": "unreadable_source", "file": name})
    try:
        config = json.loads((ROOT / "config/profiles/ventuno_q.json").read_text())
        for section, flag in PRIVACY_FLAGS:
            if config.get(section, {}).get(flag) is not False:
                findings.append({"type": "unsafe_profile_flag",
                                 "key": section + "." + flag})
        if config.get("llm", {}).get("provider") != "geniex":
            findings.append({"type": "unexpected_llm_provider"})
        count["ventuno_profile_checked"] += 1
    except (ValueError, OSError, AttributeError):
        findings.append({"type": "invalid_ventuno_profile"})
    ignore = (ROOT / ".gitignore").read_text()
    for pattern in ("*.db", "*.db-wal", "*.db-shm", "*.py[cod]", "runtime/"):
        if pattern not in ignore:
            findings.append({"type": "missing_ignore_pattern", "pattern": pattern})
    print("MYAI_STATIC_AUDIT_JSON=" + json.dumps({
        "source_only": True,
        "counts": dict(count),
        "blocking_findings": findings,
        "manual_review_flags": warnings[:100],
        "manual_review_total": len(warnings),
        "result": "PASS" if not findings else "FAIL"
    }, sort_keys=True))
    return not findings
if __name__ == "__main__":
    sys.exit(0 if audit() else 1)
