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


def test_active_runtime_contains_no_legacy_pi_assumptions():
    forbidden = (
        "from modules.pi",
        "import modules.pi",
        "pi_gpio_reference",
        "pi_system_status",
        "pi_interfaces_status",
        "pi_power_status",
        "vcgencmd",
        "IQ-8275",
    )
    roots = (
        "core",
        "modules",
        "scripts",
        "config",
    )
    suffixes = {
        ".py",
        ".json",
        ".sh",
    }
    violations = []

    for root_name in roots:
        root = (
            PROJECT_ROOT
            / root_name
        )

        for path in root.rglob(
            "*"
        ):
            if (
                not path.is_file()
                or path.suffix
                not in suffixes
            ):
                continue

            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            for token in forbidden:
                if token in text:
                    violations.append(
                        (
                            str(
                                path.relative_to(
                                    PROJECT_ROOT
                                )
                            ),
                            token,
                        )
                    )

    assert violations == []


def test_reserved_router_uart_is_referenced_only_by_ventuno_guard_code():
    allowed = {
        (
            PROJECT_ROOT
            / "modules"
            / "ventuno"
            / "platform.py"
        ).resolve(),
    }
    unexpected = []

    for root_name in (
        "core",
        "modules",
        "scripts",
        "config",
    ):
        root = (
            PROJECT_ROOT
            / root_name
        )

        for path in root.rglob(
            "*"
        ):
            if (
                not path.is_file()
                or path.suffix
                not in {
                    ".py",
                    ".json",
                    ".sh",
                }
            ):
                continue

            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            if (
                "/dev/ttyHS1"
                in text
                and path.resolve()
                not in allowed
            ):
                unexpected.append(
                    str(
                        path.relative_to(
                            PROJECT_ROOT
                        )
                    )
                )

    assert unexpected == []


def test_ble_is_optional_not_a_base_runtime_dependency():
    base = (
        PROJECT_ROOT
        / "requirements.txt"
    ).read_text(
        encoding="utf-8"
    )
    bluetooth = (
        PROJECT_ROOT
        / "requirements-bluetooth.txt"
    ).read_text(
        encoding="utf-8"
    )

    assert "bleak" not in base.lower()
    assert "bleak==3.0.2" in bluetooth


def test_pre_hardware_ventuno_profile_avoids_background_router_and_hardware_cost():
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
        "tool_routing"
    ][
        "llm_fallback_enabled"
    ] is False
    assert profile[
        "hardware_watch"
    ][
        "enabled"
    ] is False
