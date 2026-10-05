from copy import deepcopy
from types import SimpleNamespace

from core.config import DEFAULT_SETTINGS
from core.deployment_lock import (
    LOCK_SCHEMA_VERSION,
)
from core.ventuno_preflight import (
    DEFAULT_ROUTER_SOCKET,
    run_ventuno_preflight,
)


def ventuno_settings():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["llm"][
        "provider"
    ] = "geniex"
    settings["geniex"][
        "model"
    ] = (
        "ai-hub-models/"
        "Qwen3-4B-Instruct-2507"
    )
    settings["geniex"][
        "base_url"
    ] = (
        "http://127.0.0.1:18181/v1"
    )
    settings["ventuno"][
        "enabled"
    ] = True
    settings["ventuno"][
        "rpc_enabled"
    ] = False
    settings["ventuno"][
        "rpc_write_enabled"
    ] = False

    # Physical features remain disabled before board validation.
    settings["camera"][
        "enabled"
    ] = False
    settings["voice"][
        "enabled"
    ] = False
    settings["location"][
        "enabled"
    ] = False
    settings["trusted_terminals"][
        "enabled"
    ] = False
    settings["hardware_watch"][
        "enabled"
    ] = False
    settings["vision"][
        "enabled"
    ] = False
    return settings


def _statuses(
    result,
):
    return {
        item["name"]: item["status"]
        for item in result["checks"]
    }


def fake_geniex_runner(
    command,
    *,
    model_present=True,
):
    if command[-1] == "--version":
        return SimpleNamespace(
            returncode=0,
            stdout="geniex 0.8.0\n",
            stderr="",
        )

    if command[-2:] == [
        "model",
        "list",
    ]:
        output = (
            "Qwen3-4B-Instruct-2507\n"
            "Qwen3-VL-4B-Instruct\n"
            if model_present
            else "Qwen3-1.7B\n"
        )
        return SimpleNamespace(
            returncode=0,
            stdout=output,
            stderr="",
        )

    raise AssertionError(
        f"oväntat kommando: {command}"
    )


def safe_preflight(
    settings=None,
    **overrides,
):
    kwargs = {
        "machine": "aarch64",
        "system": "Linux",
        "python_version": "3.12.7",
        "board_model": (
            "Arduino VENTUNO Q "
            "Qualcomm QCS8275"
        ),
        "which": lambda name: (
            "/usr/bin/geniex"
            if name == "geniex"
            else None
        ),
        "path_exists": (
            lambda path: (
                path
                == DEFAULT_ROUTER_SOCKET
            )
        ),
        "module_available": (
            lambda name: False
        ),
        "command_runner": (
            lambda command: (
                fake_geniex_runner(
                    command,
                    model_present=True,
                )
            )
        ),
    }
    kwargs.update(
        overrides
    )
    return run_ventuno_preflight(
        settings
        or ventuno_settings(),
        **kwargs,
    )


def test_preflight_passes_safe_ventuno_core_requirements():
    result = safe_preflight()
    statuses = _statuses(
        result
    )

    assert result["passed"] is True
    assert statuses[
        "Linux ARM64"
    ] == "PASS"
    assert statuses[
        "Python 3.12"
    ] == "PASS"
    assert statuses[
        "VENTUNO board identity"
    ] == "PASS"
    assert statuses[
        "GenieX CLI"
    ] == "PASS"
    assert statuses[
        "Arduino Router Bridge Python"
    ] == "SKIP"
    assert statuses[
        "Arduino Router Unix-socket"
    ] == "SKIP"
    assert statuses[
        "STM32 RPC-skrivskydd"
    ] == "PASS"
    assert statuses[
        "VENTUNO VLM"
    ] == "SKIP"


def test_preflight_rejects_nonlocal_geniex_endpoint():
    settings = ventuno_settings()
    settings["geniex"][
        "base_url"
    ] = (
        "http://192.168.1.10:18181/v1"
    )

    result = safe_preflight(
        settings
    )

    assert result["passed"] is False
    assert (
        _statuses(
            result
        )[
            "Lokal GenieX-endpoint"
        ]
        == "FAIL"
    )


def test_rpc_disabled_does_not_require_router_bridge():
    result = safe_preflight(
        module_available=lambda name: False,
        path_exists=lambda path: False,
    )
    statuses = _statuses(
        result
    )

    assert result["passed"] is True
    assert statuses[
        "Arduino Router Bridge Python"
    ] == "SKIP"
    assert statuses[
        "Arduino Router Unix-socket"
    ] == "SKIP"


def test_rpc_enabled_requires_router_bridge_and_socket():
    settings = ventuno_settings()
    settings["ventuno"][
        "rpc_enabled"
    ] = True
    settings["ventuno"][
        "rpc_allowed_read_methods"
    ] = [
        "myai_ping"
    ]

    result = safe_preflight(
        settings,
        module_available=lambda name: False,
        path_exists=lambda path: False,
    )
    statuses = _statuses(
        result
    )

    assert result["passed"] is False
    assert statuses[
        "Arduino Router Bridge Python"
    ] == "FAIL"
    assert statuses[
        "Arduino Router Unix-socket"
    ] == "FAIL"


def test_rpc_enabled_passes_with_bridge_and_socket():
    settings = ventuno_settings()
    settings["ventuno"][
        "rpc_enabled"
    ] = True
    settings["ventuno"][
        "rpc_allowed_read_methods"
    ] = [
        "myai_ping"
    ]

    result = safe_preflight(
        settings,
        module_available=lambda name: (
            name
            == "arduino.router_bridge"
        ),
        path_exists=lambda path: (
            path
            == DEFAULT_ROUTER_SOCKET
        ),
    )

    assert result["passed"] is True


def test_preflight_flags_enabled_rpc_writes_without_claiming_safe():
    settings = ventuno_settings()
    settings["ventuno"][
        "rpc_enabled"
    ] = True
    settings["ventuno"][
        "rpc_write_enabled"
    ] = True
    settings["ventuno"][
        "rpc_allowed_read_methods"
    ] = [
        "myai_ping"
    ]
    settings["ventuno"][
        "rpc_allowed_write_methods"
    ] = [
        "example_write"
    ]

    result = safe_preflight(
        settings,
        module_available=lambda name: True,
        path_exists=lambda path: True,
    )

    assert (
        _statuses(
            result
        )[
            "STM32 RPC-skrivskydd"
        ]
        == "WARN"
    )


def test_preflight_requires_geniex_provider_cli_and_arm64():
    settings = ventuno_settings()
    settings["llm"][
        "provider"
    ] = "ollama"

    result = run_ventuno_preflight(
        settings,
        machine="x86_64",
        system="Windows",
        python_version="3.12.7",
        board_model="",
        which=lambda name: None,
        path_exists=lambda path: False,
        module_available=lambda name: False,
    )
    statuses = _statuses(
        result
    )

    assert result["passed"] is False
    assert statuses[
        "Linux ARM64"
    ] == "FAIL"
    assert statuses[
        "GenieX LLM-provider"
    ] == "FAIL"
    assert statuses[
        "GenieX CLI"
    ] == "FAIL"


def test_preflight_warns_on_non_312_python_without_false_hardware_claim():
    result = safe_preflight(
        python_version="3.11.9",
    )

    assert result["passed"] is True
    assert (
        _statuses(
            result
        )[
            "Python 3.12"
        ]
        == "WARN"
    )


def test_preflight_warns_if_board_identity_cannot_be_read():
    result = safe_preflight(
        board_model="",
    )

    assert result["passed"] is True
    assert (
        _statuses(
            result
        )[
            "VENTUNO board identity"
        ]
        == "WARN"
    )


def test_preflight_reads_geniex_version_and_confirms_model():
    result = safe_preflight()
    statuses = _statuses(
        result
    )

    assert statuses[
        "GenieX version"
    ] == "PASS"
    assert statuses[
        "GenieX chipset-modell"
    ] == "PASS"
    assert result["passed"] is True


def test_preflight_blocks_model_not_listed_for_chipset():
    result = safe_preflight(
        command_runner=lambda command: (
            fake_geniex_runner(
                command,
                model_present=False,
            )
        ),
    )

    assert (
        _statuses(
            result
        )[
            "GenieX chipset-modell"
        ]
        == "FAIL"
    )
    assert result["passed"] is False


def test_preflight_warns_when_geniex_model_list_command_fails():
    def runner(
        command,
    ):
        if command[-1] == "--version":
            return SimpleNamespace(
                returncode=0,
                stdout="geniex 0.8.0",
                stderr="",
            )

        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="catalog unavailable",
        )

    result = safe_preflight(
        command_runner=runner,
    )

    assert (
        _statuses(
            result
        )[
            "GenieX chipset-modell"
        ]
        == "WARN"
    )
    assert result["passed"] is True


def test_enabled_camera_requires_opencv():
    settings = ventuno_settings()
    settings["camera"][
        "enabled"
    ] = True

    result = safe_preflight(
        settings,
        module_available=lambda name: False,
    )

    assert result["passed"] is False
    assert (
        _statuses(
            result
        )[
            "VENTUNO camera dependency"
        ]
        == "FAIL"
    )


def test_enabled_voice_requires_current_fallback_dependencies():
    settings = ventuno_settings()
    settings["voice"][
        "enabled"
    ] = True

    result = safe_preflight(
        settings,
        module_available=lambda name: False,
    )
    statuses = _statuses(
        result
    )

    assert result["passed"] is False
    assert statuses[
        "VENTUNO microphone dependency"
    ] == "FAIL"
    assert statuses[
        "VENTUNO VAD dependency"
    ] == "FAIL"
    assert statuses[
        "VENTUNO STT dependency"
    ] == "FAIL"


def test_enabled_gps_requires_pyserial():
    settings = ventuno_settings()
    settings["location"][
        "enabled"
    ] = True
    settings["location"][
        "serial_port"
    ] = "/dev/ttyUSB0"

    result = safe_preflight(
        settings,
        module_available=lambda name: False,
    )

    assert result["passed"] is False
    assert (
        _statuses(
            result
        )[
            "VENTUNO GPS dependency"
        ]
        == "FAIL"
    )


def _locked_stack(
    version="geniex 0.8.0",
):
    return {
        "platform": {
            "system": "Linux",
            "machine": "aarch64",
            "python": "3.12.7",
        },
        "geniex": {
            "version": version,
        },
        "packages": {
            "requests": "2.32.5",
            "psutil": "7.1.0",
            "bleak": "3.0.2",
            "arduino-router-bridge": "0.5.0",
        },
        "files": {
            "requirements.txt": {
                "sha256": "main",
            },
            "requirements-ventuno.txt": {
                "sha256": "ventuno",
            },
            "requirements-camera.txt": {
                "sha256": "camera",
            },
            "requirements-voice.txt": {
                "sha256": "voice",
            },
            "requirements-gps.txt": {
                "sha256": "gps",
            },
        },
        "models": {
            "llm": (
                "ai-hub-models/"
                "Qwen3-4B-Instruct-2507"
            ),
            "vision": None,
        },
    }


def test_preflight_passes_matching_required_deployment_lock(
    tmp_path,
):
    settings = ventuno_settings()
    settings["deployment_lock"][
        "required"
    ] = True
    settings["deployment_lock"][
        "lock_path"
    ] = (
        "config/"
        "ventuno_stack_lock.json"
    )
    observed = _locked_stack()
    manifest = {
        "schema_version": (
            LOCK_SCHEMA_VERSION
        ),
        "locked": True,
        "expected": observed,
    }

    result = safe_preflight(
        settings,
        deployment_observer=(
            lambda current, root: (
                observed
            )
        ),
        deployment_manifest_loader=(
            lambda path: manifest
        ),
        project_root=tmp_path,
    )

    assert (
        _statuses(
            result
        )[
            "VENTUNO deployment lock"
        ]
        == "PASS"
    )
    assert result["passed"] is True


def test_preflight_blocks_required_deployment_lock_mismatch(
    tmp_path,
):
    settings = ventuno_settings()
    settings["deployment_lock"][
        "required"
    ] = True
    observed = _locked_stack(
        "geniex 0.9.0"
    )
    manifest = {
        "schema_version": (
            LOCK_SCHEMA_VERSION
        ),
        "locked": True,
        "expected": _locked_stack(
            "geniex 0.8.0"
        ),
    }

    result = safe_preflight(
        settings,
        deployment_observer=(
            lambda current, root: (
                observed
            )
        ),
        deployment_manifest_loader=(
            lambda path: manifest
        ),
        project_root=tmp_path,
    )

    assert (
        _statuses(
            result
        )[
            "VENTUNO deployment lock"
        ]
        == "FAIL"
    )
    assert result["passed"] is False
