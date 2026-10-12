"""Read-only QNN CLI profiling gate for the installed VENTUNO runtime.

Requests only qnn-net-run --help; never loads a context, performs inference,
edits services, reads user data, or changes accelerator state.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

GRAPH_SELECTORS = frozenset({
    "--graph", "--graphs", "--graph_name", "--graph_names",
    "--graph_list", "--select_graph", "--select_graphs",
})
REQUIRED_OPTIONS = frozenset({
    "--backend", "--retrieve_context", "--input_list", "--profiling_level",
})
RELEVANT_OPTIONS = REQUIRED_OPTIONS | GRAPH_SELECTORS | frozenset({
    "--config_file", "--output_dir", "--profiling_option",
    "--use_native_input_files", "--use_native_output_files", "--op_packages",
})


def parse_flags(text: str) -> frozenset[str]:
    """Extract standalone long options; do not expose raw CLI help/logs."""
    return frozenset(re.findall(r"(?<![\w-])--[a-zA-Z][a-zA-Z0-9_-]*", text))


def assess_help(help_text: str, exit_code: int = 0) -> dict[str, object]:
    flags = parse_flags(help_text)
    selectors = sorted(flags & GRAPH_SELECTORS)
    missing = sorted(REQUIRED_OPTIONS - flags)
    if exit_code != 0:
        status = "inconclusive-help-error"
    elif missing:
        status = "no-go-missing-required-options"
    elif selectors:
        status = "review-graph-selection-semantics"
    else:
        status = "no-go-no-explicit-graph-selector"
    return {
        "status": status,
        "help_exit_code": exit_code,
        "graph_selectors": selectors,
        "required_missing": missing,
        "relevant_flags": sorted(flags & RELEVANT_OPTIONS),
        "direct_npu_profile_verified": False,
        "service_changes_allowed": False,
    }


def inspect_installed_cli() -> dict[str, object]:
    binary = shutil.which("qnn-net-run")
    if not binary:
        return {"status": "no-go-cli-not-found", "direct_npu_profile_verified": False}
    try:
        result = subprocess.run(
            [binary, "--help"], capture_output=True, text=True,
            errors="replace", timeout=8, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "inconclusive-help-unavailable",
            "error_type": type(exc).__name__,
            "direct_npu_profile_verified": False,
        }
    return assess_help(result.stdout + "\n" + result.stderr, result.returncode)


def main() -> int:
    print("QNN net-run graph-selection capability preflight (read-only)")
    print(json.dumps(inspect_installed_cli(), sort_keys=True))
    print("A CLI flag is not proof of multi-context compatibility or valid model inputs.")
    print("No QNN context loaded; do not pause MyAI/GenieX based on this check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
