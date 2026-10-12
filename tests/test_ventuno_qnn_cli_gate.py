"""Safety and capability tests for read-only QNN profiling gate."""
from scripts.ventuno_qnn_cli_gate import (
    assess_help, build_single_graph_input_list_arg,
    help_documents_graph_skip, parse_flags,
)


def test_parse_flags_discards_example_values():
    flags = parse_flags("qnn-net-run --backend /private/lib --input_list inputs.txt\n")
    assert flags == frozenset({"--backend", "--input_list"})


def test_no_explicit_graph_selector_is_no_go():
    report = assess_help(
        "--backend --retrieve_context --input_list --profiling_level --config_file"
    )
    assert report["status"] == "no-go-no-explicit-graph-selector"
    assert report["graph_selectors"] == []
    assert report["direct_npu_profile_verified"] is False
    assert report["service_changes_allowed"] is False


def test_selector_still_requires_semantics_review():
    report = assess_help(
        "--backend --retrieve_context --input_list --profiling_level --graph_name"
    )
    assert report["status"] == "review-graph-selection-semantics"
    assert report["graph_selectors"] == ["--graph_name"]
    assert report["direct_npu_profile_verified"] is False


def test_required_option_missing_fails_closed():
    report = assess_help("--backend --retrieve_context --graph_name")
    assert report["status"] == "no-go-missing-required-options"
    assert "--input_list" in report["required_missing"]


def test_help_error_is_inconclusive_even_with_all_flags():
    report = assess_help(
        "--backend --retrieve_context --input_list --profiling_level --graph", 1
    )
    assert report["status"] == "inconclusive-help-error"


def test_help_never_leaks_arbitrary_text():
    report = assess_help(
        "--backend --retrieve_context --input_list --profiling_level "
        "secret_token=/home/private/secret.bin"
    )
    assert "secret" not in str(report)


def test_installed_help_documents_skip_by_double_underscore():
    help_text = """
    --backend=<val> Path to a QNN backend
    --retrieve_context=<val> Cached binary
    --profiling_level=<val> basic/detailed
    --input_list=<val> Input lists for the network.
      When multiple graphs are present, to skip execution of a graph use
      "__" (double underscore) as the file name in the comma-separated list.
    """
    report = assess_help(help_text)
    assert report["status"] == "review-input-list-skip-semantics"
    assert report["input_list_skip_documented"] is True
    assert report["graph_selectors"] == []
    assert report["direct_npu_profile_verified"] is False
    assert report["service_changes_allowed"] is False


def test_skip_claim_without_sentinel_is_not_sufficient():
    text = ("--backend --retrieve_context --input_list --profiling_level "
            "When multiple graphs are present, skip execution of a graph")
    assert help_documents_graph_skip(text) is False
    assert assess_help(text)["status"] == "no-go-no-explicit-graph-selector"


def test_sentinel_without_skip_claim_is_not_sufficient():
    text = ("--backend --retrieve_context --input_list --profiling_level "
            "The output placeholder is __")
    assert help_documents_graph_skip(text) is False


def test_help_failure_cannot_confirm_skip_support():
    text = ("--backend --retrieve_context --input_list --profiling_level "
            "To skip execution of a graph use __ (double underscore)")
    report = assess_help(text, exit_code=2)
    assert report["status"] == "inconclusive-help-error"
    assert report["input_list_skip_documented"] is False


def test_graph_selector_still_requires_review_when_skip_is_documented():
    text = ("--backend --retrieve_context --input_list --profiling_level "
            "--graph_name To skip execution of a graph use __")
    report = assess_help(text)
    assert report["status"] == "review-graph-selection-semantics"
    assert report["direct_npu_profile_verified"] is False


def test_multigraph_skip_argument_has_exactly_one_selected_list():
    result = build_single_graph_input_list_arg(10, 5, "temporary/input_list.txt")
    slots = result.split(",")
    assert len(slots) == 10
    assert slots[5] == "temporary/input_list.txt"
    assert slots.count("__") == 9


def test_single_graph_has_no_skip_marker():
    assert build_single_graph_input_list_arg(1, 0, "example.txt") == "example.txt"


def test_invalid_graph_indexes_fail_closed():
    import pytest
    for total, selected in ((0, 0), (25, 0), (10, -1), (10, 10),
                            (True, 0), (10, True)):
        with pytest.raises(ValueError, match="invalid-graph-selection"):
            build_single_graph_input_list_arg(total, selected, "safe.txt")


def test_reject_unsafe_input_paths():
    import pytest
    invalid = ("__", "a,b", "a b", "-option", "../safe", "../tmp/${HOME}",
               "foo\nbar", "", "a" * 256)
    for path in invalid:
        with pytest.raises(ValueError, match="unsafe-input-list-path"):
            build_single_graph_input_list_arg(10, 5, path)


def test_build_plan_never_opens_files(tmp_path):
    missing_path = str(tmp_path / "nonexistent.raw")
    output = build_single_graph_input_list_arg(2, 1, missing_path)
    assert output.endswith(missing_path)
    assert not (tmp_path / "nonexistent.raw").exists()


def test_context_list_cli_flag_does_not_verify_geniex_compatibility():
    text = ("--backend --retrieve_context --retrieve_context_list "
            "--input_list --profiling_level")
    report = assess_help(text)
    assert report["context_list_cli_flag_present"] is True
    assert "--retrieve_context_list" in report["relevant_flags"]
    assert report["geniex_multicontext_execution_compatibility_proven"] is False
    assert report["service_changes_allowed"] is False


def test_context_list_flag_from_failed_help_does_not_count():
    text = ("--backend --retrieve_context --retrieve_context_list "
            "--input_list --profiling_level")
    report = assess_help(text, exit_code=1)
    assert report["context_list_cli_flag_present"] is False
    assert report["direct_npu_profile_verified"] is False
