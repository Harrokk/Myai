"""Two independent, offline/source-only passes over every tracked MyAI file.

Neither pass imports project modules, executes tools, opens hardware, loads a
model, changes systemd or contacts the network. Designed to support a human
line-by-line review, not to 'certify' runtime safety.
"""
from __future__ import annotations

import ast
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
HIGH_RISK = {"subprocess.Popen", "eval", "exec", "os.system",
             "os.popen", "pickle.loads", "marshal.loads"}
SENSITIVE_WORKFLOW = re.compile(
    r"(arecord|aplay|consent.to.record|consent_to_record|"
    r"qnn-net-run|systemctl\s+(?:stop|restart)|"
    r"geniex\s+serve|tiny_qnn_htp_once)", re.I,
)


def _name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return parent + "." + node.attr if parent else node.attr
    return ""


def _tracked(root):
    raw = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=20,
    ).stdout
    return [
        x.decode("utf-8", "surrogateescape")
        for x in raw.split(b"\0") if x
    ]


def _tool_names(tree):
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and t.id == "TOOLS" for t in targets):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            continue
        for key in value.keys:
            if isinstance(key, ast.Constant) and type(key.value) is str:
                found.append(key.value)
    return found


def logic_pass(root, files):
    inventory = Counter()
    tests = []
    tools = defaultdict(list)
    source_without_test_tokens = []
    syntax_errors = []
    module_imports = defaultdict(set)
    runtime_file_paths = []
    for name in files:
        file = root / name
        if not file.is_file() or file.is_symlink():
            inventory["missing_or_symlinked"] += 1
            continue
        inventory["tracked_files"] += 1
        folder = name.split("/")[0] if "/" in name else "<root>"
        inventory["area_" + folder] += 1
        if file.suffix != ".py":
            continue
        inventory["python_files"] += 1
        try:
            code = file.read_text(encoding="utf-8-sig")
            tree = ast.parse(code, filename=name)
        except (OSError, UnicodeError, SyntaxError):
            syntax_errors.append(name)
            continue
        inventory["python_valid"] += 1
        if name.startswith("tests/"):
            tests.append(name)
            inventory["test_functions"] += sum(
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name.startswith("test_") for n in ast.walk(tree)
            )
        if name.startswith("modules/"):
            for key in _tool_names(tree):
                tools[key].append(name)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(("core.", "modules.", "scripts.")):
                module_imports[name].add(node.module)
            if isinstance(node, ast.Call) and _name(node.func) in {"open", "os.open", "Path.write_text"}:
                inventory["filesystem_api_calls"] += 1
    for key, paths in tools.items():
        if len(paths) > 1:
            source_without_test_tokens.append({
                "tool": key, "files": sorted(paths),
            })
    return {
        "inventory": dict(sorted(inventory.items())),
        "tool_name_count": len(tools),
        "tool_name_collisions": source_without_test_tokens[:24],
        "invalid_python_files": syntax_errors[:25],
        "test_module_count": len(tests),
        "importing_python_files_count": len(module_imports),
        "tracked_files_inspected": len(files),
    }


def security_pass(root, files):
    inventory = Counter()
    prod_sensitive_calls = []
    runner_push_workflows = []
    hardware_workflow_candidates = []
    dependency_files = []
    json_failures = []
    suspicious_top_level = []
    for name in files:
        file = root / name
        if not file.is_file() or file.is_symlink():
            continue
        if name.startswith(".github/workflows/") and file.suffix in {".yml", ".yaml"}:
            inventory["workflow_files"] += 1
            data = file.read_text(encoding="utf-8", errors="replace")
            push = re.search(r"(?m)^\s{2}push:\s*$", data) is not None
            manual = re.search(r"(?m)^\s{2}workflow_dispatch:\s*$", data) is not None
            runner = "self-hosted" in data
            inventory["self_hosted_workflow_files"] += runner
            inventory["push_triggered_workflow_files"] += push
            inventory["manual_trigger_workflow_files"] += manual
            if runner and push:
                runner_push_workflows.append(name)
            if runner and push and SENSITIVE_WORKFLOW.search(data):
                hardware_workflow_candidates.append(name)
            if re.search(r"(?m)^\s*pull_request_target\s*:", data):
                inventory["pull_request_target_workflows"] += 1
            if re.search(r"(?m)^\s*contents\s*:\s*write\s*$", data):
                inventory["workflow_contents_write_permission"] += 1
        if name.startswith("requirements") and name.endswith(".txt"):
            dependency_files.append(name)
            for row in file.read_text(encoding="utf-8", errors="replace").splitlines():
                s = row.strip()
                if not s or s.startswith("#"):
                    continue
                inventory["direct_requirements"] += 1
                if "==" not in s:
                    inventory["version_range_requirements"] += 1
                if "--hash=" not in s:
                    inventory["requirements_without_hash"] += 1
        if file.suffix == ".json":
            inventory["json_files"] += 1
            try:
                json.loads(file.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError):
                json_failures.append(name)
        if file.suffix != ".py":
            continue
        try:
            tree = ast.parse(file.read_text(encoding="utf-8-sig"), filename=name)
        except (OSError, UnicodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call = _name(node.func)
            if call in HIGH_RISK:
                inventory["sensitive_code_calls"] += 1
                if not name.startswith("tests/"):
                    prod_sensitive_calls.append({
                        "file": name, "line": node.lineno, "call": call,
                    })
            if call.startswith("subprocess."):
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        inventory["shell_true_calls"] += 1
                        if not name.startswith("tests/"):
                            prod_sensitive_calls.append({
                                "file": name, "line": node.lineno, "call": "shell=True",
                            })
        if name.startswith(("core/", "modules/")):
            for stmt in tree.body:
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    func = _name(stmt.value.func)
                    if func not in {"print"}:
                        suspicious_top_level.append({"file": name, "line": stmt.lineno, "call": func})
    profile = json.loads((root / "config/profiles/ventuno_q.json").read_text())
    # Explicit load_settings(path=profile) merges the in-code defaults,
    # NOT config/settings.json; derive that AST literal without import.
    default_tree = ast.parse((root / "core/config.py").read_text())
    def default_section(name):
        for assignment in default_tree.body:
            if not isinstance(assignment, ast.Assign):
                continue
            if not any(isinstance(t, ast.Name) and t.id == "DEFAULT_SETTINGS"
                       for t in assignment.targets):
                continue
            if not isinstance(assignment.value, ast.Dict):
                break
            for key, value in zip(assignment.value.keys, assignment.value.values):
                if isinstance(key, ast.Constant) and key.value == name:
                    return ast.literal_eval(value)
        raise ValueError("Unresolved source default config section")
    voice = profile.get("voice", {})
    default_voice = default_section("voice")
    default_memory = default_section("memory")
    return {
        "inventory": dict(sorted(inventory.items())),
        "production_sensitive_calls": prod_sensitive_calls[:70],
        "top_level_production_call_candidates": suspicious_top_level[:30],
        "self_hosted_push_workflows": runner_push_workflows[:65],
        "self_hosted_push_hardware_candidates": hardware_workflow_candidates[:65],
        "requirements_files": dependency_files,
        "invalid_json_files": json_failures[:20],
        "ventuno_profile": {
            "voice_enabled": voice.get("enabled"),
            "tts_enabled": voice.get("tts_enabled"),
            "stt_model": voice.get("stt_model", default_voice.get("stt_model")),
            "isolation_enabled": voice.get(
                "stt_process_isolation_enabled",
                default_voice.get("stt_process_isolation_enabled"),
            ),
            "persistent_stt_enabled": voice.get(
                "stt_persistent_worker_enabled",
                default_voice.get("stt_persistent_worker_enabled"),
            ),
            "llm_streaming_enabled": voice.get("llm_streaming_enabled"),
            "deployment_lock_required": profile.get("deployment_lock", {}).get("required"),
            "rpc_write_enabled": profile.get("ventuno", {}).get("rpc_write_enabled"),
            "default_memory_auto_save_enabled": default_memory.get("auto_save_enabled"),
            "voice_default_tts_provider": voice.get("tts_provider", default_voice.get("tts_provider")),
            "voice_default_stt_device": voice.get("stt_device", default_voice.get("stt_device")),
            "voice_backup_model_count": len(voice.get("backup_stt_models", default_voice.get("backup_stt_models", []))),
        },
    }


def audit(root=ROOT):
    files = _tracked(root)
    logic = logic_pass(root, files)
    security = security_pass(root, files)
    errors = []
    if logic["invalid_python_files"]:
        errors.append("invalid_python")
    if logic["tool_name_collisions"]:
        errors.append("duplicate_tools_registry")
    if security["invalid_json_files"]:
        errors.append("invalid_json")
    if logic["inventory"].get("missing_or_symlinked"):
        errors.append("missing_or_linked_repo_file")
    if security["inventory"].get("shell_true_calls"):
        errors.append("shell_true_requires_manual_review")
    return {
        "status": "source-audit-completed" if not errors else "source-audit-with-findings",
        "revision": "exact-run-checkout",
        "passes": {"logic": logic, "security": security},
        "automatic_blockers": errors,
        "actual_physical_tests_performed": False,
        "safe_to_deploy_automatically": False,
        "audit_does_not_prove_functional_coverage": True,
    }


def audit_exit_code(result):
    """Fail CI when either the report is incomplete or any blocker exists.

    Returning 0 for a completed scan that *found* a blocker previously let
    source-audit-with-findings pass as though it had cleared the release gate.
    Validate the result shape defensively; malformed results are not clean.
    """
    if not isinstance(result, dict):
        return 2
    blockers = result.get("automatic_blockers")
    if (result.get("status") != "source-audit-completed"
            or not isinstance(blockers, list)
            or blockers
            or result.get("safe_to_deploy_automatically") is not False
            or result.get("actual_physical_tests_performed") is not False):
        return 2
    return 0


def main():
    try:
        result = audit()
    except Exception:
        # Do not expose file contents, exception values, environment or paths.
        result = {
            "status": "source-audit-incomplete",
            "automatic_blockers": ["audit_error"],
            "safe_to_deploy_automatically": False,
            "actual_physical_tests_performed": False,
        }
    print("MYAI_TWO_PASS_DEEP_AUDIT_JSON=" + json.dumps(result, sort_keys=True))
    return audit_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
