from copy import deepcopy

import pytest

from core.config import (
    DEFAULT_SETTINGS,
    PROJECT_ROOT,
    load_settings,
)
from core.config_validation import (
    require_valid_settings,
    validate_settings,
)


def test_default_settings_are_valid():
    result = validate_settings(
        deepcopy(
            DEFAULT_SETTINGS
        )
    )

    assert result["valid"] is True
    assert result["errors"] == []


def test_ventuno_profile_requirements_pass_for_safe_profile():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["llm"]["provider"] = "geniex"
    settings["ventuno"]["enabled"] = True
    settings["assistant"][
        "current_platform"
    ] = "Arduino VENTUNO Q"

    result = validate_settings(
        settings,
        require_ventuno_profile=True,
    )

    assert result["valid"] is True


def test_invalid_llm_provider_is_blocking():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["llm"]["provider"] = "mystery"

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "invalid_llm_provider"
        for item in result[
            "errors"
        ]
    )


def test_geniex_provider_requires_local_loopback_endpoint():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["llm"]["provider"] = "geniex"
    settings["geniex"][
        "base_url"
    ] = "http://192.168.1.50:18181/v1"

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "geniex_not_loopback"
        for item in result[
            "errors"
        ]
    )


def test_enabled_fallback_requires_model():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["llm"]["fallback"][
        "enabled"
    ] = True

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "fallback_model_missing"
        for item in result[
            "errors"
        ]
    )


def test_health_aware_without_fallback_is_warning_not_error():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["llm"]["fallback"][
        "health_aware"
    ]["enabled"] = True

    result = validate_settings(
        settings
    )

    assert result["valid"] is True
    assert any(
        item["code"]
        == "health_aware_inactive"
        for item in result[
            "warnings"
        ]
    )


def test_restart_requires_nonempty_argument_list():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["geniex_supervisor"][
        "enabled"
    ] = True
    settings["geniex_supervisor"][
        "restart_enabled"
    ] = True
    settings["geniex_supervisor"][
        "restart_command"
    ] = "systemctl restart geniex"

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "unsafe_restart_command"
        for item in result[
            "errors"
        ]
    )


def test_rpc_write_requires_rpc_and_allowlist():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["ventuno"][
        "rpc_write_enabled"
    ] = True

    result = validate_settings(
        settings
    )

    codes = {
        item["code"]
        for item in result[
            "errors"
        ]
    }
    assert "rpc_write_without_rpc" in codes
    assert (
        "rpc_write_allowlist_missing"
        in codes
    )


def test_enabled_vision_requires_model():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["vision"][
        "enabled"
    ] = True

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "vision_model_missing"
        for item in result[
            "errors"
        ]
    )


def test_require_valid_settings_raises_on_blocking_error():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["llm"][
        "provider"
    ] = "broken"

    with pytest.raises(
        ValueError,
        match="Ogiltig MyAI-konfiguration",
    ):
        require_valid_settings(
            settings
        )



def test_selfdev_promotion_requires_selfdev():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["selfdev"]["promotion_enabled"] = True

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "selfdev_promotion_without_selfdev"
        for item in result["errors"]
    )


def test_selfdev_cannot_disable_bubblewrap_requirement():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["selfdev"]["enabled"] = True
    settings["selfdev"]["require_bubblewrap"] = False

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "selfdev_requires_bubblewrap"
        for item in result["errors"]
    )


def test_required_deployment_lock_requires_path():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["deployment_lock"]["required"] = True
    settings["deployment_lock"]["lock_path"] = ""

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "deployment_lock_path_missing"
        for item in result["errors"]
    )


def test_enabled_error_logging_requires_path():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["error_logging"]["path"] = ""

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "error_log_path_missing"
        for item in result["errors"]
    )


def test_error_logging_message_limit_has_safe_minimum():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["error_logging"][
        "max_message_chars"
    ] = 10

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "error_log_message_limit_invalid"
        for item in result["errors"]
    )


def test_error_logging_recent_limit_is_bounded():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["error_logging"][
        "recent_limit"
    ] = 51

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "error_log_recent_limit_invalid"
        for item in result["errors"]
    )


def test_stability_analysis_limits_are_validated():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["stability_analysis"][
        "max_records"
    ] = 100001
    settings["stability_analysis"][
        "trend_fraction"
    ] = 0.05

    result = validate_settings(
        settings
    )

    codes = {
        item["code"]
        for item in result["errors"]
    }
    assert (
        "stability_max_records_invalid"
        in codes
    )
    assert (
        "stability_trend_fraction_invalid"
        in codes
    )


def test_stability_analysis_requires_log_path():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["stability_analysis"][
        "log_path"
    ] = ""

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "stability_log_path_missing"
        for item in result["errors"]
    )


def test_memory_lifecycle_threshold_order_is_validated():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"][
        "conflict_similarity_threshold"
    ] = 0.8
    settings["memory"][
        "supersede_similarity_threshold"
    ] = 0.7

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "memory_supersede_threshold_too_low"
        for item in result["errors"]
    )


def test_memory_lifecycle_scan_and_stale_limits_are_validated():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"][
        "max_conflict_scan"
    ] = 1001
    settings["memory"][
        "stale_after_days"
    ] = -1

    result = validate_settings(
        settings
    )

    codes = {
        item["code"]
        for item in result["errors"]
    }
    assert "memory_conflict_scan_invalid" in codes
    assert "memory_stale_after_days_invalid" in codes


def test_required_audit_cannot_be_disabled():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["audit_logging"][
        "enabled"
    ] = False
    settings["audit_logging"][
        "require_for_writes"
    ] = True

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "audit_required_but_disabled"
        for item in result["errors"]
    )


def test_enabled_audit_requires_path_and_safe_limits():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["audit_logging"][
        "path"
    ] = ""
    settings["audit_logging"][
        "max_detail_chars"
    ] = 10
    settings["audit_logging"][
        "recent_limit"
    ] = 51

    result = validate_settings(
        settings
    )

    codes = {
        item["code"]
        for item in result["errors"]
    }
    assert "audit_log_path_missing" in codes
    assert "audit_detail_limit_invalid" in codes
    assert "audit_recent_limit_invalid" in codes


def test_diagnostics_runtime_stale_limit_is_validated():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["diagnostics"][
        "runtime_stale_seconds"
    ] = 0

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "diagnostics_runtime_stale_invalid"
        for item in result["errors"]
    )


def test_unknown_config_key_is_blocking():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["voice"][
        "stt_langauge"
    ] = "sv"

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "unknown_config_key"
        and "voice.stt_langauge"
        in item["message"]
        for item in result["errors"]
    )


def test_config_schema_version_mismatch_is_blocking():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings[
        "schema_version"
    ] = 999

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "unsupported_config_schema"
        for item in result["errors"]
    )


def test_versioned_repository_profiles_validate_cleanly():
    main = load_settings(
        PROJECT_ROOT
        / "config"
        / "settings.json"
    )
    ventuno = load_settings(
        PROJECT_ROOT
        / "config"
        / "profiles"
        / "ventuno_q.json"
    )

    main_result = validate_settings(
        main
    )
    ventuno_result = validate_settings(
        ventuno,
        require_ventuno_profile=True,
    )

    assert main_result[
        "valid"
    ] is True
    assert main_result[
        "errors"
    ] == []
    assert ventuno_result[
        "valid"
    ] is True
    assert ventuno_result[
        "errors"
    ] == []


def test_fx_enabled_requires_internet():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["fx"][
        "enabled"
    ] = True
    settings["internet"][
        "enabled"
    ] = False

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "fx_requires_internet"
        for item in result[
            "errors"
        ]
    )


def test_fx_provider_target_url_and_age_are_fail_closed():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["fx"].update(
        {
            "provider": "unknown",
            "target_currency": "USD",
            "ecb_url": "https://example.com/rates.xml",
            "max_age_days": 99,
        }
    )

    result = validate_settings(
        settings
    )
    codes = {
        item["code"]
        for item in result[
            "errors"
        ]
    }

    assert "fx_provider_invalid" in codes
    assert "fx_target_currency_invalid" in codes
    assert "fx_ecb_url_invalid" in codes
    assert "fx_max_age_days_invalid" in codes


def test_default_fx_configuration_is_valid_while_disabled():
    settings = deepcopy(DEFAULT_SETTINGS)

    result = validate_settings(
        settings
    )

    assert not any(
        item["code"].startswith(
            "fx_"
        )
        for item in result[
            "errors"
        ]
    )


def test_enabled_weather_requires_internet():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["weather"][
        "enabled"
    ] = True
    settings["internet"][
        "enabled"
    ] = False

    result = validate_settings(
        settings
    )

    assert result["valid"] is False
    assert any(
        item["code"]
        == "weather_requires_internet"
        for item in result["errors"]
    )


def test_weather_rejects_unapproved_hosts_and_forecast_range():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["weather"][
        "geocoding_url"
    ] = "https://example.com/search"
    settings["weather"][
        "forecast_url"
    ] = "https://example.com/forecast"
    settings["weather"][
        "forecast_days"
    ] = 8

    result = validate_settings(
        settings
    )

    codes = {
        item["code"]
        for item in result["errors"]
    }
    assert (
        "weather_geocoding_url_invalid"
        in codes
    )
    assert (
        "weather_forecast_url_invalid"
        in codes
    )
    assert (
        "weather_forecast_days_invalid"
        in codes
    )


def test_weather_config_accepts_safe_open_meteo_endpoints():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["weather"][
        "enabled"
    ] = True
    settings["internet"][
        "enabled"
    ] = True
    settings["weather"][
        "default_location"
    ] = "Stockholm"

    result = validate_settings(
        settings
    )

    assert result["valid"] is True


def test_memory_administration_limits_are_validated():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"][
        "administration_limit"
    ] = 201
    settings["memory"][
        "stale_review_days"
    ] = 0

    result = validate_settings(
        settings
    )

    codes = {
        item["code"]
        for item in result["errors"]
    }
    assert (
        "memory_administration_limit_invalid"
        in codes
    )
    assert (
        "memory_stale_review_days_invalid"
        in codes
    )


def test_orchestration_bounds_are_validated():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["orchestration"][
        "max_tools"
    ] = 1
    settings["orchestration"][
        "max_result_chars_per_tool"
    ] = 100
    settings["orchestration"][
        "enabled"
    ] = "yes"
    settings["orchestration"][
        "allow_local_capture"
    ] = "yes"

    result = validate_settings(
        settings
    )

    codes = {
        item["code"]
        for item in result["errors"]
    }
    assert (
        "orchestration_max_tools_invalid"
        in codes
    )
    assert (
        "orchestration_result_limit_invalid"
        in codes
    )
    assert (
        "orchestration_enabled_invalid"
        in codes
    )
    assert (
        "orchestration_capture_flag_invalid"
        in codes
    )


def test_default_orchestration_config_is_valid():
    settings = deepcopy(DEFAULT_SETTINGS)

    result = validate_settings(
        settings
    )

    assert not any(
        item["code"].startswith(
            "orchestration_"
        )
        for item in result[
            "errors"
        ]
    )
