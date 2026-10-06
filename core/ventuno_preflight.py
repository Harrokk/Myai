import importlib.util
import platform
import subprocess
from pathlib import Path
import shutil
from urllib.parse import urlparse

from core.deployment_lock import (
    collect_ventuno_stack,
    load_lock_manifest,
    resolve_project_path,
    verify_ventuno_stack,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parent.parent

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
    python_version=None,
    board_model=None,
    which=None,
    path_exists=None,
    module_available=None,
    command_runner=None,
    deployment_observer=None,
    deployment_manifest_loader=None,
    project_root=None,
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
    deployment_observer = (
        deployment_observer
        or collect_ventuno_stack
    )
    deployment_manifest_loader = (
        deployment_manifest_loader
        or load_lock_manifest
    )
    project_root = Path(
        project_root
        if project_root is not None
        else PROJECT_ROOT
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
    python_version = (
        python_version
        if python_version is not None
        else platform.python_version()
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

    normalized_python = str(
        python_version
        or ""
    )
    checks.append(
        _check(
            "Python 3.12",
            (
                "PASS"
                if normalized_python.startswith(
                    "3.12"
                )
                else "WARN"
            ),
            (
                f"python={normalized_python or 'okänd'}; "
                "Arduino VENTUNO-exempel använder Python 3.12"
            ),
        )
    )

    if board_model is None:
        try:
            board_model = (
                Path(
                    "/proc/device-tree/model"
                )
                .read_text(
                    encoding="utf-8"
                )
                .strip(
                    "\x00\n "
                )
            )
        except (
            OSError,
            UnicodeError,
        ):
            board_model = ""

    normalized_board = str(
        board_model
        or ""
    ).lower()
    board_recognized = any(
        marker in normalized_board
        for marker in (
            "ventuno",
            "qcs8275",
        )
    )
    checks.append(
        _check(
            "VENTUNO board identity",
            (
                "PASS"
                if board_recognized
                else "WARN"
            ),
            (
                str(
                    board_model
                    or (
                        "board identity kunde inte verifieras "
                        "read-only; kontrollera fysisk VENTUNO Q"
                    )
                )
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

    ventuno = settings.get(
        "ventuno",
        {},
    )
    rpc_enabled = bool(
        ventuno.get(
            "rpc_enabled",
            False,
        )
    )
    bridge_available = (
        module_available(
            "arduino.router_bridge"
        )
    )

    if rpc_enabled:
        checks.append(
            _check(
                "Arduino Router Bridge Python",
                (
                    "PASS"
                    if bridge_available
                    else "FAIL"
                ),
                (
                    "arduino.router_bridge kan importeras"
                    if bridge_available
                    else (
                        "RPC är aktiverat men arduino.router_bridge "
                        "saknas; installera requirements-ventuno.txt."
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
                    else "FAIL"
                ),
                str(
                    DEFAULT_ROUTER_SOCKET
                ),
            )
        )
    else:
        checks.append(
            _check(
                "Arduino Router Bridge Python",
                "SKIP",
                "VENTUNO RPC är avstängt.",
            )
        )
        checks.append(
            _check(
                "Arduino Router Unix-socket",
                "SKIP",
                "VENTUNO RPC är avstängt.",
            )
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

    feature_dependencies = []

    excel = settings.get(
        "excel",
        {},
    )
    if excel.get(
        "enabled",
        False,
    ):
        feature_dependencies.append(
            (
                "VENTUNO Excel dependency",
                "openpyxl",
                "excel.enabled=true kräver openpyxl; "
                "installera requirements-excel.txt.",
            )
        )

    camera = settings.get(
        "camera",
        {},
    )
    if camera.get(
        "enabled",
        True,
    ):
        feature_dependencies.append(
            (
                "VENTUNO camera dependency",
                "cv2",
                "camera.enabled=true kräver OpenCV.",
            )
        )

    voice = settings.get(
        "voice",
        {},
    )
    if voice.get(
        "enabled",
        False,
    ):
        feature_dependencies.extend(
            [
                (
                    "VENTUNO microphone dependency",
                    "sounddevice",
                    "voice.enabled=true kräver sounddevice.",
                ),
                (
                    "VENTUNO VAD dependency",
                    "webrtcvad",
                    "voice.enabled=true kräver webrtcvad.",
                ),
                (
                    "VENTUNO STT dependency",
                    "faster_whisper",
                    "voice.enabled=true kräver faster-whisper "
                    "tills verifierad Qualcomm-provider finns.",
                ),
            ]
        )

        if voice.get(
            "tts_enabled",
            False,
        ):
            feature_dependencies.append(
                (
                    "VENTUNO TTS dependency",
                    "pyttsx3",
                    "voice.tts_enabled=true kräver pyttsx3 "
                    "för nuvarande fallback-provider.",
                )
            )

    location = settings.get(
        "location",
        {},
    )
    if location.get(
        "enabled",
        False,
    ):
        feature_dependencies.append(
            (
                "VENTUNO GPS dependency",
                "serial",
                "location.enabled=true kräver pyserial.",
            )
        )

    terminals = settings.get(
        "trusted_terminals",
        {},
    )
    if (
        terminals.get(
            "enabled",
            False,
        )
        and str(
            terminals.get(
                "connector_provider",
                "",
            )
        ).strip().lower()
        == "bleak_gatt"
    ):
        feature_dependencies.append(
            (
                "VENTUNO Bluetooth dependency",
                "bleak",
                "bleak_gatt kräver bleak.",
            )
        )

    for name, module_name, details in feature_dependencies:
        checks.append(
            _check(
                name,
                (
                    "PASS"
                    if module_available(
                        module_name
                    )
                    else "FAIL"
                ),
                (
                    f"{module_name} kan importeras"
                    if module_available(
                        module_name
                    )
                    else details
                ),
            )
        )

    hardware_watch = settings.get(
        "hardware_watch",
        {},
    )
    if hardware_watch.get(
        "enabled",
        False,
    ):
        commands = {
            name: bool(
                which(
                    name
                )
            )
            for name in (
                "lsusb",
                "lspci",
            )
        }
        checks.append(
            _check(
                "VENTUNO hardware inventory tools",
                (
                    "PASS"
                    if any(
                        commands.values()
                    )
                    else "WARN"
                ),
                (
                    " ".join(
                        f"{name}={'ja' if present else 'nej'}"
                        for name, present in commands.items()
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

    deployment_lock = settings.get(
        "deployment_lock",
        {},
    )

    if deployment_lock.get(
        "required",
        False,
    ):
        raw_lock_path = str(
            deployment_lock.get(
                "lock_path",
                "",
            )
            or ""
        ).strip()

        if not raw_lock_path:
            checks.append(
                _check(
                    "VENTUNO deployment lock",
                    "FAIL",
                    "deployment_lock.lock_path saknas",
                )
            )
        else:
            try:
                lock_path = resolve_project_path(
                    project_root,
                    raw_lock_path,
                )
                manifest = (
                    deployment_manifest_loader(
                        lock_path
                    )
                )
                observed = deployment_observer(
                    settings,
                    project_root,
                )
                verification = (
                    verify_ventuno_stack(
                        manifest,
                        observed,
                    )
                )

                if verification["passed"]:
                    checks.append(
                        _check(
                            "VENTUNO deployment lock",
                            "PASS",
                            (
                                "observerad mjukvarustack "
                                "matchar versionslåset"
                            ),
                        )
                    )
                else:
                    details = (
                        verification["errors"][0]
                        if verification["errors"]
                        else (
                            "mismatch: "
                            + verification[
                                "mismatches"
                            ][0]["path"]
                        )
                    )
                    checks.append(
                        _check(
                            "VENTUNO deployment lock",
                            "FAIL",
                            details,
                        )
                    )
            except Exception as error:
                checks.append(
                    _check(
                        "VENTUNO deployment lock",
                        "FAIL",
                        (
                            "versionslåset kunde inte "
                            f"verifieras: {error}"
                        ),
                    )
                )
    else:
        checks.append(
            _check(
                "VENTUNO deployment lock",
                "SKIP",
                (
                    "versionslåsning är avstängd tills "
                    "den fysiska VENTUNO-stacken har "
                    "verifierats"
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
            "python": str(
                python_version
            ),
            "board_model": str(
                board_model
                or ""
            ),
        },
        "checks": checks,
        "passed": not failures,
        "failure_count": len(
            failures
        ),
    }
