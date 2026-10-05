from copy import deepcopy

import pytest

from core.config import DEFAULT_SETTINGS
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
