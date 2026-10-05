import importlib.util
import platform
import subprocess
from pathlib import Path
import shutil
from urllib.parse import urlparse


DEFAULT_ROUTER_SOCKET = Path(
    "/var/run/arduino-router.sock"
)


def _check(name, status, details):
    return {
        "name": name,
        "status": status,
        "details": details,
    }


def _module_available(name):
    try:
        return (
            importlib.util.find_spec(
                name
            )
            is not None
        )
    except (
        ImportError,
        ModuleNotFoundError,
        AttributeError,
    ):
        return False


def _is_loopback_http(url):
    try:
        parsed = urlparse(
            str(url or "")
        )
    except ValueError:
        return False

    return (
        parsed.scheme == "http"
        and parsed.hostname
        in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
    )


def _default_command_runner(command):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _command_text(result):
    stdout = str(
        getattr(
            result,
            "stdout",
            "",
        )
        or ""
    ).strip()
    stderr = str(
        getattr(
            result,
            "stderr",
            "",
        )
        or ""
    ).strip()

    return (
        stdout
        if stdout
        else stderr
    )


def _model_list_contains(
    output,
    configured_model,
):
    text = str(
        output
        or ""
    ).lower()
    model = str(
        configured_model
        or ""
    ).strip().lower()

    if not text or not model:
        return False

    candidates = {
        model,
        model.removeprefix(
            "ai-hub-models/"
        ),
        model.split("/")[-1],
    }

    return any(
        candidate
        and candidate in text
        for candidate in candidates
    )


def run_ventuno_preflight(
    settings,
    *,
    machine=None,
    system=None,
    which=None,
    path_exists=None,
    module_available=None,
    command_runner=None,
):
    """Read-only checks. Does not connect to STM32 and does not run inference."""

    which = which or shutil.which
    path_exists = (
        path_exists
        or (lambda path: Path(path).exists())
    )
    module_available = (
        module_available
        or _module_available
    )
    command_runner = (
        command_runner
        or _default_command_runner
    )
    machine = (
        machine
        if machine is not None
        else platform.machine()
    )
    system = (
        system
        if system is not None
        else platform.system()
    )

    checks = []
    normalized_machine = str(
        machine or ""
    ).lower()

    checks.append(
        _check(
            "Linux ARM64",
            (
                "PASS"
                if (
                    str(system).lower()
                    == "linux"
                    and normalized_machine
                    in {
                        "aarch64",
                        "arm64",
                    }
                )
                else "FAIL"
            ),
            (
                f"system={system}, "
                f"machine={machine}"
            ),
        )
    )

    llm = settings.get(
        "llm",
        {},
    )
    provider = str(
        llm.get(
            "provider",
            "",
        )
    ).strip().lower()
    checks.append(
        _check(
            "GenieX LLM-provider",
            (
                "PASS"
                if provider == "geniex"
                else "FAIL"
            ),
            f"provider={provider or 'saknas'}",
        )
    )

    geniex = settings.get(
        "geniex",
        {},
    )
    base_url = geniex.get(
        "base_url",
        "",
    )
    checks.append(
        _check(
            "Lokal GenieX-endpoint",
            (
                "PASS"
                if _is_loopback_http(
                    base_url
                )
                else "FAIL"
            ),
            str(
                base_url
                or "saknas"
            ),
        )
    )

    model = str(
        geniex.get(
            "model",
            "",
        )
        or ""
    ).strip()
    checks.append(
        _check(
            "GenieX LLM-modell",
            (
                "PASS"
                if model
                else "FAIL"
            ),
            model or "saknas",
        )
    )

    geniex_path = which(
        "geniex"
    )
    checks.append(
        _check(
            "GenieX CLI",
            (
                "PASS"
                if geniex_path
                else "FAIL"
            ),
            (
                str(geniex_path)
                if geniex_path
                else "geniex hittades inte i PATH"
            ),
        )
    )

    if geniex_path:
        try:
            version_result = command_runner(
                [
                    str(geniex_path),
                    "--version",
                ]
            )
            version_text = _command_text(
                version_result
            )
            version_ok = (
                getattr(
                    version_result,
                    "returncode",
                    1,
                )
                == 0
                and bool(version_text)
            )
            checks.append(
                _check(
                    "GenieX version",
                    (
                        "PASS"
                        if version_ok
                        else "WARN"
                    ),
                    (
                        version_text
                        or "version kunde inte läsas"
                    ),
                )
            )
        except Exception as error:
            checks.append(
                _check(
                    "GenieX version",
                    "WARN",
                    f"versionskontroll misslyckades: {error}",
                )
            )

        try:
            model_result = command_runner(
                [
                    str(geniex_path),
                    "model",
                    "list",
                ]
            )
            model_output = _command_text(
                model_result
            )
            model_command_ok = (
                getattr(
                    model_result,
                    "returncode",
                    1,
                )
                == 0
            )

            if model_command_ok:
                compatible = (
                    _model_list_contains(
                        model_output,
                        model,
                    )
                )
                checks.append(
                    _check(
                        "GenieX chipset-modell",
                        (
                            "PASS"
                            if compatible
                            else "FAIL"
                        ),
                        (
                            model
                            if compatible
                            else (
                                f"{model or 'saknas'} hittades inte "
                                "i geniex model list"
                            )
                        ),
                    )
                )
            else:
                checks.append(
                    _check(
                        "GenieX chipset-modell",
                        "WARN",
                        (
                            model_output
                            or "geniex model list misslyckades"
                        ),
                    )
                )
        except Exception as error:
            checks.append(
                _check(
                    "GenieX chipset-modell",
                    "WARN",
                    f"modellistan kunde inte läsas: {error}",
                )
            )
    else:
        checks.append(
            _check(
                "GenieX version",
                "SKIP",
                "CLI saknas",
            )
        )
        checks.append(
            _check(
                "GenieX chipset-modell",
                "SKIP",
                "CLI saknas",
            )
        )

    bridge_available = (
        module_available(
            "arduino.router_bridge"
        )
    )
    checks.append(
        _check(
            "Arduino Router Bridge Python",
            (
                "PASS"
                if bridge_available
                else "WARN"
            ),
            (
                "arduino.router_bridge kan importeras"
                if bridge_available
                else (
                    "Valfritt beroende saknas; "
                    "installera requirements-ventuno.txt."
                )
            ),
        )
    )

    socket_present = path_exists(
        DEFAULT_ROUTER_SOCKET
    )
    checks.append(
        _check(
            "Arduino Router Unix-socket",
            (
                "PASS"
                if socket_present
                else "WARN"
            ),
            str(
                DEFAULT_ROUTER_SOCKET
            ),
        )
    )

    ventuno = settings.get(
        "ventuno",
        {},
    )
    write_enabled = bool(
        ventuno.get(
            "rpc_write_enabled",
            False,
        )
    )
    checks.append(
        _check(
            "STM32 RPC-skrivskydd",
            (
                "PASS"
                if not write_enabled
                else "WARN"
            ),
            (
                "skrivning avstängd"
                if not write_enabled
                else (
                    "skrivning är aktiverad; "
                    "verifiera allowlist före fysisk test."
                )
            ),
        )
    )

    vision = settings.get(
        "vision",
        {},
    )

    if vision.get(
        "enabled",
        False,
    ):
        vision_provider = str(
            vision.get(
                "provider",
                "",
            )
        ).strip().lower()
        vision_model = str(
            vision.get(
                "model",
                "",
            )
            or ""
        ).strip()
        checks.append(
            _check(
                "VENTUNO VLM",
                (
                    "PASS"
                    if (
                        vision_provider
                        == "geniex"
                        and vision_model
                    )
                    else "FAIL"
                ),
                (
                    f"provider={vision_provider or 'saknas'}, "
                    f"model={vision_model or 'saknas'}"
                ),
            )
        )
    else:
        checks.append(
            _check(
                "VENTUNO VLM",
                "SKIP",
                (
                    "vision är avstängd tills "
                    "fysisk kamera/NPU-verifiering görs"
                ),
            )
        )

    failures = [
        item
        for item in checks
        if item["status"]
        == "FAIL"
    ]

    return {
        "platform": {
            "system": str(system),
            "machine": str(machine),
        },
        "checks": checks,
        "passed": not failures,
        "failure_count": len(
            failures
        ),
    }
