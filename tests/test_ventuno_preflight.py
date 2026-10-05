from copy import deepcopy
from types import SimpleNamespace

from core.config import DEFAULT_SETTINGS
from core.ventuno_preflight import (
    DEFAULT_ROUTER_SOCKET,
    run_ventuno_preflight,
)


def ventuno_settings():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["llm"]["provider"] = "geniex"
    settings["geniex"]["model"] = (
        "ai-hub-models/Qwen3-4B-Instruct-2507"
    )
    settings["geniex"]["base_url"] = (
        "http://127.0.0.1:18181/v1"
    )
    settings["ventuno"]["enabled"] = True
    settings["ventuno"]["rpc_write_enabled"] = False
    return settings


def _statuses(result):
    return {
        item["name"]: item["status"]
        for item in result["checks"]
    }


def test_preflight_passes_safe_ventuno_core_requirements():
    result = run_ventuno_preflight(
        ventuno_settings(),
        machine="aarch64",
        system="Linux",
        which=lambda name: (
            "/usr/bin/geniex"
            if name == "geniex"
            else None
        ),
        path_exists=lambda path: (
            path
            == DEFAULT_ROUTER_SOCKET
        ),
        module_available=lambda name: (
            name
            == "arduino.router_bridge"
        ),
    )

    statuses = _statuses(
        result
    )

    assert result["passed"] is True
    assert statuses["Linux ARM64"] == "PASS"
    assert statuses["GenieX CLI"] == "PASS"
    assert (
        statuses[
            "Arduino Router Unix-socket"
        ]
        == "PASS"
    )
    assert (
        statuses[
            "STM32 RPC-skrivskydd"
        ]
        == "PASS"
    )
    assert statuses["VENTUNO VLM"] == "SKIP"


def test_preflight_rejects_nonlocal_geniex_endpoint():
    settings = ventuno_settings()
    settings["geniex"]["base_url"] = (
        "http://192.168.1.10:18181/v1"
    )

    result = run_ventuno_preflight(
        settings,
        machine="aarch64",
        system="Linux",
        which=lambda name: "/usr/bin/geniex",
        path_exists=lambda path: True,
        module_available=lambda name: True,
    )

    assert result["passed"] is False
    assert (
        _statuses(result)[
            "Lokal GenieX-endpoint"
        ]
        == "FAIL"
    )


def test_preflight_warns_but_does_not_fail_on_optional_bridge():
    result = run_ventuno_preflight(
        ventuno_settings(),
        machine="aarch64",
        system="Linux",
        which=lambda name: "/usr/bin/geniex",
        path_exists=lambda path: False,
        module_available=lambda name: False,
    )

    statuses = _statuses(
        result
    )

    assert result["passed"] is True
    assert (
        statuses[
            "Arduino Router Bridge Python"
        ]
        == "WARN"
    )
    assert (
        statuses[
            "Arduino Router Unix-socket"
        ]
        == "WARN"
    )


def test_preflight_flags_enabled_rpc_writes():
    settings = ventuno_settings()
    settings["ventuno"]["rpc_write_enabled"] = True

    result = run_ventuno_preflight(
        settings,
        machine="aarch64",
        system="Linux",
        which=lambda name: "/usr/bin/geniex",
        path_exists=lambda path: True,
        module_available=lambda name: True,
    )

    assert result["passed"] is True
    assert (
        _statuses(result)[
            "STM32 RPC-skrivskydd"
        ]
        == "WARN"
    )


def test_preflight_requires_geniex_provider_and_cli():
    settings = ventuno_settings()
    settings["llm"]["provider"] = "ollama"

    result = run_ventuno_preflight(
        settings,
        machine="x86_64",
        system="Windows",
        which=lambda name: None,
        path_exists=lambda path: False,
        module_available=lambda name: False,
    )

    assert result["passed"] is False
    assert result["failure_count"] == 3



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


def test_preflight_reads_geniex_version_and_confirms_model():
    result = run_ventuno_preflight(
        ventuno_settings(),
        machine="aarch64",
        system="Linux",
        which=lambda name: "/usr/bin/geniex",
        path_exists=lambda path: True,
        module_available=lambda name: True,
        command_runner=lambda command: (
            fake_geniex_runner(
                command,
                model_present=True,
            )
        ),
    )

    statuses = _statuses(result)

    assert statuses["GenieX version"] == "PASS"
    assert (
        statuses["GenieX chipset-modell"]
        == "PASS"
    )
    assert result["passed"] is True


def test_preflight_blocks_model_not_listed_for_chipset():
    result = run_ventuno_preflight(
        ventuno_settings(),
        machine="aarch64",
        system="Linux",
        which=lambda name: "/usr/bin/geniex",
        path_exists=lambda path: True,
        module_available=lambda name: True,
        command_runner=lambda command: (
            fake_geniex_runner(
                command,
                model_present=False,
            )
        ),
    )

    statuses = _statuses(result)

    assert (
        statuses["GenieX chipset-modell"]
        == "FAIL"
    )
    assert result["passed"] is False


def test_preflight_warns_when_geniex_model_list_command_fails():
    def runner(command):
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

    result = run_ventuno_preflight(
        ventuno_settings(),
        machine="aarch64",
        system="Linux",
        which=lambda name: "/usr/bin/geniex",
        path_exists=lambda path: True,
        module_available=lambda name: True,
        command_runner=runner,
    )

    assert (
        _statuses(result)[
            "GenieX chipset-modell"
        ]
        == "WARN"
    )
    assert result["passed"] is True
