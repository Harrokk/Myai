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
