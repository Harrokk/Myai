import importlib.util
import platform
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


def run_ventuno_preflight(
    settings,
    *,
    machine=None,
    system=None,
    which=None,
    path_exists=None,
    module_available=None,
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
