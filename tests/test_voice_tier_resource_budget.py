"""Purely illustrative input values; NO measurements of VENTUNO here."""
import pytest

from core.voice_tier_resource_budget import evaluate_tiered_ram_budget


def check(available_mib=9000, *, peaks=None, geniex=3000,
          headroom=1024, mode="sequential", cleaned=True):
    if peaks is None:
        peaks = {"parakeet": 1800, "canary": 2600, "whisper": 3200}
    return evaluate_tiered_ram_budget(
        available_mib=available_mib,
        stt_peak_rss_mib=peaks,
        future_geniex_peak_mib=geniex,
        headroom_mib=headroom,
        mode=mode,
        cleanup_verified=cleaned,
    )


def test_sequential_budget_uses_max_model_not_sum_after_proven_cleanup():
    a = check()
    assert a["eligible_for_trial"] is True
    assert a["required_mib"] == 3200 + 1024


def test_parallel_budget_sums_all_models_and_geniex():
    a = check(mode="parallel")
    assert a["required_mib"] == 1800 + 2600 + 3200 + 3000 + 1024
    assert a["eligible_for_trial"] is False


def test_sequential_cannot_assume_cleanup_was_successful():
    a = check(cleaned=False)
    assert a["eligible_for_trial"] is False
    assert a["reason"] == "no_verified_stt_cleanup"


def test_missing_model_measurement_blocks():
    a = check(peaks={"canary": 2200, "whisper": 3100})
    assert a["eligible_for_trial"] is False
    assert a["reason"] == "missing_or_invalid_stt_measurements"


@pytest.mark.parametrize("invalid", [
    None, 0, -1, True, 4.5, "16000", float("inf"), 65537,
])
def test_unmeasured_or_malformed_available_memory_is_not_accepted(invalid):
    a = check(available_mib=invalid)
    assert a["eligible_for_trial"] is False


def test_exact_limit_is_a_planning_pass_not_execution_authorization():
    assert check(available_mib=4224)["eligible_for_trial"] is True
    assert check(available_mib=4223)["eligible_for_trial"] is False


def test_bad_cleanup_status_blocks():
    a = check(cleaned="true")
    assert a["reason"] == "invalid_cleanup_status"


def test_invalid_loading_strategy_blocks():
    a = check(mode="streaming-parallel")
    assert a["reason"] == "unsupported_loading_mode"


def test_budget_keeps_headroom_not_just_peak_model_rss():
    assert check(available_mib=3500)["eligible_for_trial"] is False


def test_empty_memory_measurements_never_justify_hardware_trial():
    a = check(peaks={})
    assert a["eligible_for_trial"] is False


def test_parallel_does_not_depend_on_release_signal():
    a = check(available_mib=16000, mode="parallel", cleaned=False)
    assert a["eligible_for_trial"] is True
    assert a["required_mib"] == 11624


def test_cannot_hide_unmeasured_third_model_behind_zero_or_boolean():
    for bad in (0, True, None, "2200"):
        a = check(peaks={"parakeet": 1800, "canary": bad, "whisper": 3200})
        assert a["eligible_for_trial"] is False
