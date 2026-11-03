"""The new voice policy must remain impossible to enable before wiring."""
from copy import deepcopy

from core.config import DEFAULT_SETTINGS
from core.config_validation import validate_settings


def error_codes(settings):
    return {
        item["code"] for item in validate_settings(settings)["errors"]
    }


def test_tiered_mode_is_default_off():
    assert DEFAULT_SETTINGS["voice"]["risk_tiered_verification_enabled"] is False


def test_tiered_mode_cannot_enable_before_production_authorization_wiring():
    config = deepcopy(DEFAULT_SETTINGS)
    config["voice"]["risk_tiered_verification_enabled"] = True
    assert "risk_tiered_verification_not_integrated" in error_codes(config)


def test_non_boolean_toggle_is_rejected():
    config = deepcopy(DEFAULT_SETTINGS)
    config["voice"]["risk_tiered_verification_enabled"] = "yes"
    assert "hardware_flag_not_boolean" in error_codes(config)


def test_new_flag_default_does_not_introduce_activation_error():
    assert "risk_tiered_verification_not_integrated" not in error_codes(
        deepcopy(DEFAULT_SETTINGS)
    )
