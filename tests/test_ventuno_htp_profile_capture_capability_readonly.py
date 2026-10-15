"""Synthetic-only QAIRT-HTP profiling capture capability regressions."""
import json
import pytest
from scripts import ventuno_htp_profile_capture_capability_readonly as gate


def packs(version="2.46.0-0ubuntu1"):
    return {
        "qairt-libs": {"status": "installed", "version": version},
        "qairt-dsp-binaries": {"status": "installed", "version": version},
    }


def helpflags(*options):
    return {
        "available": True,
        "profile_relevant_flags": list(options),
        "help_exit": 0,
    }


def good_metadata(*, ver="2.46.0-0ubuntu1",
                  geniex=(), netrun=("--profiling_level",),
                  viewer=("--input_log", "--reader")):
    return gate.classify(
        packs(ver), helpflags(*geniex), helpflags(*netrun),
        helpflags(*viewer), "aarch64",
    )


def test_installed_246_does_not_qualify_upstream_geniex_optrace_248():
    r = good_metadata()
    assert r["installed_runtime_minor_is_246"] is True
    assert r["upstream_plugin_optrace_min_runtime"] == "2.48"
    assert r["upstream_plugin_optrace_runtime_requirement_met"] is False
    assert "upstream_geniex_optrace_min_248_not_met_or_unknown" in r["observations"]
    assert r["qnn_net_run_profiling_flag_observed"] is True
    assert r["qnn_profile_viewer_input_flag_observed"] is True
    assert r["installed_geniex_cli_optrace_option_observed"] is False
    assert r["status"] == "no_go_direct_htp_profile_not_yet_reproducible"


def test_even_248_plus_cli_flag_does_not_assert_in_process_profile():
    r = good_metadata(
        ver="2.48.0", geniex=("--enable-optrace",),
    )
    assert r["upstream_plugin_optrace_runtime_requirement_met"] is True
    assert r["installed_geniex_cli_optrace_option_observed"] is True
    assert r["installed_geniex_plugin_optrace_supported_verified"] is False
    assert r["live_inprocess_qnn_profile_session_verified"] is False
    assert r["htp_per_op_cycles_measured"] is False
    assert r["model_graph_placement_verified"] is False


@pytest.mark.parametrize("minor,expected", [
    ("2.45", True), ("2.46", True), ("2.47", True),
    ("2.48", False), ("2.49", False), ("3.0", False),
])
def test_upstream_minimum_version_policy(minor, expected):
    r = gate.classify(
        packs(minor + ".0"), helpflags("--enable-optrace"),
        helpflags("--profiling_level"), helpflags("--input_log"),
        "aarch64",
    )
    assert ("upstream_geniex_optrace_min_248_not_met_or_unknown"
            in r["observations"]) is expected
    if minor.startswith("3."):
        assert r["upstream_plugin_optrace_runtime_requirement_met"] is False


@pytest.mark.parametrize("bad", [
    None, False, "2.46.0", "2.46-x", "/private/SECRET", "2",
    "9999999.1", "", "2.46\nSECRET", 2.46,
])
def test_malformed_minor_never_verifies_optrace(bad):
    assert gate.parse_minor(bad) is None


@pytest.mark.parametrize("bad", [
    None, {}, [], {"profile_relevant_flags": "profiling"},
    {"profile_relevant_flags": [123]}, {"profile_relevant_flags": [True]},
    {"profile_relevant_flags": ["/private/foo"]},
])
def test_invalid_help_results_do_not_create_positive_flags(bad):
    assert gate._flags(bad) == set()


def test_untrusted_runtime_package_mismatch_fails_closed():
    p = packs()
    p["qairt-dsp-binaries"]["version"] = "2.48.0"
    r = gate.classify(
        p, helpflags("--enable-optrace"),
        helpflags("--profiling_level"), helpflags("--input_log"),
        "aarch64",
    )
    assert r["runtime_and_dsp_minor_match"] is False
    assert "qairstack_runtime_pair_not_attested" in r["observations"]
    assert r["htp_per_op_cycles_measured"] is False


def test_only_log_and_token_timings_are_not_vendor_qnn_trace():
    r = good_metadata(
        geniex=("--log", "--compute", "--profile"),
        netrun=("--backend",), viewer=("--help",),
    )
    assert r["installed_geniex_cli_optrace_option_observed"] is False
    assert r["qnn_net_run_profiling_flag_observed"] is False
    assert r["qnn_profile_viewer_input_flag_observed"] is False
    assert r["status"].startswith("no_go")


def test_no_raw_help_or_pkg_values_can_escape():
    huge = "SECRET_KEY at /home/arduino/private/model_cache"
    p = packs()
    p["qairt-libs"]["version"] = huge
    r = gate.classify(
        p, {"available": True, "profile_relevant_flags": [huge]},
        {"available": True, "profile_relevant_flags": [huge]},
        {"available": True, "profile_relevant_flags": [huge]},
        "aarch64",
    )
    s = json.dumps(r)
    assert "SECRET_KEY" not in s
    assert "/home/" not in s
    assert r["raw_cli_output_or_paths_exported"] is False
    assert r["profile_log_or_private_model_read"] is False
    assert r["live_service_restart_or_stop_performed"] is False
    assert r["new_model_or_qnn_client_started"] is False


def test_report_uses_only_vendor_package_and_help_probe_metadata(monkeypatch):
    recorded = []
    monkeypatch.setattr(gate, "package_versions", lambda: packs())
    def fake_help(bin_name, subcommand=None):
        recorded.append((bin_name, subcommand))
        return helpflags("--profiling_level", "--input_log")
    monkeypatch.setattr(gate, "command_help", fake_help)
    monkeypatch.setattr(gate.platform, "machine", lambda: "aarch64")
    r = gate.report()
    assert recorded == [
        ("geniex", "serve"),
        ("qnn-net-run", None),
        ("qnn-profile-viewer", None),
    ]
    assert r["target_is_aarch64"] is True
    assert r["qnn_net_run_is_separate_inference_process"] is True
    assert r["live_inprocess_qnn_profile_session_verified"] is False


def test_missing_or_wrong_target_is_no_go():
    r = gate.classify(
        {}, {}, {}, {}, "x86_64",
    )
    assert "not_on_ventuno_arm64" in r["observations"]
    assert "qairstack_runtime_pair_not_attested" in r["observations"]
    assert r["htp_per_op_cycles_measured"] is False
