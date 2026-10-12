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


def help_documents_graph_skip(help_text: str) -> bool:
    """Check whether the *installed* CLI documents multi-graph skip markers.

    The documented qnn-net-run multi-graph input-list accepts "__" in the
    comma-separated list to skip a graph. This detects help text only; it
    must not be interpreted as compatibility with cached GenieX binaries.
    """
    normalized = " ".join(help_text.casefold().split())
    sentinel = (
        "double underscore" in normalized
        or re.search(r'(?<![a-z0-9_])["\x27`]?__["\x27`]?(?![a-z0-9_])', normalized)
        is not None
    )
    skip_statement = (
        "skip execution of a graph" in normalized
        or "skip executing a graph" in normalized
        or "skip execution of graphs" in normalized
    )
    return bool(sentinel and skip_statement and "--input_list" in normalized)


def assess_help(help_text: str, exit_code: int = 0) -> dict[str, object]:
    flags = parse_flags(help_text)
    selectors = sorted(flags & GRAPH_SELECTORS)
    missing = sorted(REQUIRED_OPTIONS - flags)
    documented_skip = help_documents_graph_skip(help_text)
    if exit_code != 0:
        status = "inconclusive-help-error"
    elif missing:
        status = "no-go-missing-required-options"
    elif selectors:
        status = "review-graph-selection-semantics"
    elif documented_skip:
        status = "review-input-list-skip-semantics"
    else:
        status = "no-go-no-explicit-graph-selector"
    return {
        "status": status,
        "help_exit_code": exit_code,
        "graph_selectors": selectors,
        "input_list_skip_documented": documented_skip if exit_code == 0 else False,
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
    print("CLI help alone cannot verify graph order, shared-weight loading or valid model inputs.")
    print("No QNN context loaded; do not pause MyAI/GenieX based on this check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
