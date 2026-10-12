"""Safety and capability tests for read-only QNN profiling gate."""
from scripts.ventuno_qnn_cli_gate import assess_help, parse_flags


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
