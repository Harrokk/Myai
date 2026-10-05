import json
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]


def test_legacy_raspberry_pi_runtime_is_removed():
    assert not (
        PROJECT_ROOT
        / "modules"
        / "pi"
    ).exists()
    assert not (
        PROJECT_ROOT
        / "scripts"
        / "pi_hardware_validation.py"
    ).exists()


def test_active_tool_routing_has_no_pi_plugin_names():
    text = (
        PROJECT_ROOT
        / "core"
        / "tool_manager.py"
    ).read_text(
        encoding="utf-8"
    )

    assert "pi_gpio_reference" not in text
    assert "pi_system_status" not in text
    assert "pi_interfaces_status" not in text
    assert "mentions_pi" not in text


def test_ventuno_profile_targets_qcs8275_and_geniex():
    profile = json.loads(
        (
            PROJECT_ROOT
            / "config"
            / "profiles"
            / "ventuno_q.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert profile[
        "assistant"
    ][
        "current_platform"
    ] == "Arduino VENTUNO Q"
    assert "QCS8275" in profile[
        "assistant"
    ][
        "gpu"
    ]
    assert "QCS8275" in profile[
        "assistant"
    ][
        "future_target"
    ]
    assert "IQ-8275" not in str(
        profile
    )
    assert profile[
        "llm"
    ][
        "provider"
    ] == "geniex"
    assert profile[
        "ventuno"
    ][
        "enabled"
    ] is True
    assert profile[
        "ventuno"
    ][
        "rpc_write_enabled"
    ] is False


def test_unverified_physical_features_are_explicitly_disabled():
    profile = json.loads(
        (
            PROJECT_ROOT
            / "config"
            / "profiles"
            / "ventuno_q.json"
        ).read_text(
            encoding="utf-8"
        )
    )

    assert profile[
        "camera"
    ][
        "enabled"
    ] is False
    assert profile[
        "voice"
    ][
        "enabled"
    ] is False
    assert profile[
        "voice"
    ][
        "handsfree_enabled"
    ] is False
    assert profile[
        "location"
    ][
        "enabled"
    ] is False
    assert profile[
        "trusted_terminals"
    ][
        "enabled"
    ] is False
    assert profile[
        "vision"
    ][
        "enabled"
    ] is False


def test_gps_requirements_use_real_newlines():
    text = (
        PROJECT_ROOT
        / "requirements-gps.txt"
    ).read_text(
        encoding="utf-8"
    )

    assert "\\n" not in text
    assert "pyserial>=3.5,<4" in text


def test_router_reserved_uart_is_hard_coded_as_reserved_not_general_io():
    text = (
        PROJECT_ROOT
        / "modules"
        / "ventuno"
        / "platform.py"
    ).read_text(
        encoding="utf-8"
    )

    assert '"/dev/ttyHS1"' in text
    assert "RESERVED_DEVICE_NODES" in text
    assert "Arduino Router" in text
