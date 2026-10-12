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


def build_single_graph_input_list_arg(
    graph_count: int, selected_index: int, input_list: str
) -> str:
    """Build the documented "__" skip-list for *one* graph, without running QNN.

    Positions are based on candidate metadata ordering. This is NOT proof
    that qnn-net-run maps those positions to the same graphs in a serialized
    multi-graph/multi-context GenieX bundle.
    """
    if (type(graph_count) is not int or not 1 <= graph_count <= 24
            or type(selected_index) is not int
            or not 0 <= selected_index < graph_count):
        raise ValueError("invalid-graph-selection")
    if (not isinstance(input_list, str) or not 1 <= len(input_list) <= 255
            or input_list == "__"
            or input_list.startswith("-")
            or ".." in input_list.split("/")
            or re.fullmatch(r"[A-Za-z0-9_./-]+", input_list) is None):
        raise ValueError("unsafe-input-list-path")
    return ",".join(
        input_list if index == selected_index else "__"
        for index in range(graph_count)
    )


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
    report = inspect_installed_cli()
    print(json.dumps(report, sort_keys=True))
    if report.get("input_list_skip_documented"):
        # Structural example only; the graph-to-slot mapping is still unverified.
        planned = build_single_graph_input_list_arg(
            10, 5, "SYNTHETIC_INPUT_LIST"
        )
        print("Synthetic input-list plan:", json.dumps({
            "graph_count": len(planned.split(",")),
            "selected_index": 5,
            "skip_slots": planned.split(",").count("__"),
            "model_executed": False,
        }, sort_keys=True))
    print("CLI help alone cannot verify graph order, shared-weight loading or valid model inputs.")
    print("No QNN context loaded; do not pause MyAI/GenieX based on this check.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
