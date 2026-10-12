"""Import only faster-whisper/CTranslate2 inside a throwaway ARM64 voice venv.

No WhisperModel constructor, model weight fetch, microphone, server request
or user data. Resource guard checks available RAM and disk. Pip installs
only binary wheels in the disposable RUNNER_TEMP venv, then a separate
child imports CPU-facing Python packages under 4 GiB address-space and
35s CPU limits. Reports import peak RSS, not model inference memory.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
from pathlib import Path

from scripts.ventuno_voice_wheel_staging import (
    STT_WHEELS, disk_free_bytes, mem_available_kib,
    preflight, result_of_command,
)
from scripts.ventuno_stt_wheel_preflight import inspect_resolve_report

STT_PIP_TIMEOUT = 200
IMPORT_TIMEOUT = 50
AS_LIMIT_BYTES = 4 * 1024**3
CPU_LIMIT_SECONDS = 35


def classify_import_failure(stderr: str) -> dict[str, object]:
    text = stderr[-2500:]
    exception = re.findall(
        r"(?m)^(ImportError|ModuleNotFoundError|OSError|RuntimeError|"
        r"MemoryError|ValueError):",
        text,
    )
    libraries = re.findall(
        r"lib[a-zA-Z0-9_+.-]{1,65}[.]so(?:[.][0-9]{1,2}){0,3}",
        text,
    )
    return {
        "failure": exception[-1] if exception else "unknown-import-failure",
        "missing_shared_library": libraries[-1] if libraries else None,
    }


def import_probe_command(python: Path, runner_temp: Path,
                         env: dict[str, str]) -> dict[str, object]:
    """Subprocess (never a model load), bounded by RLIMIT_AS/CPU and wall clock."""
    import resource

    def restrict():
        resource.setrlimit(resource.RLIMIT_AS, (AS_LIMIT_BYTES, AS_LIMIT_BYTES))
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (CPU_LIMIT_SECONDS, CPU_LIMIT_SECONDS),
        )

    program = (
        "import json,resource\n"
        "import ctranslate2\n"
        "import faster_whisper\n"
        "import av\n"
        "rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
        "print(json.dumps({'imports_ok':True,'peak_rss_kib':int(rss)}))\n"
    )
    try:
        proc = subprocess.run(
            [str(python), "-I", "-c", program],
            cwd=runner_temp, env=env,
            capture_output=True, text=True, errors="replace",
            check=False, timeout=IMPORT_TIMEOUT, preexec_fn=restrict,
        )
    except subprocess.TimeoutExpired:
        return {"imports_ok": False, "failure": "import-timeout"}
    except OSError:
        return {"imports_ok": False, "failure": "import-os-error"}
    if proc.returncode:
        return {"imports_ok": False, **classify_import_failure(proc.stderr)}
    try:
        data = json.loads(proc.stdout.strip())
        rss = data.get("peak_rss_kib")
        if data.get("imports_ok") is not True or type(rss) is not int or not 0 < rss < 4 * 1024**2:
            raise ValueError
    except (ValueError, TypeError, json.JSONDecodeError):
        return {"imports_ok": False, "failure": "invalid-memory-report"}
    return {
        "imports_ok": True,
        "peak_rss_mib": round(rss / 1024, 1),
        "stt_model_instantiated": False,
        "htp_npu_used": False,
    }


def stage_stt_import(sandbox_python: Path,
                     runner_temp: Path,
                     *, arm: bool | None = None) -> dict[str, object]:
    verified_arm = (
        platform.machine().lower() in ("aarch64", "arm64")
        if arm is None else arm
    )
    resources = preflight(
        mem_available_kib(), disk_free_bytes(runner_temp),
        on_arm=verified_arm,
    )
    out: dict[str, object] = {
        **resources,
        "status": "no-go-stt-import-staging",
        "stt_wheel_packages_installed_in_temp_only": False,
        "stt_python_imports_verified": False,
        "stt_import_peak_rss_mib": None,
        "stt_model_weights_downloaded": False,
        "stt_model_instantiated": False,
        "geniex_service_modified": False,
        "production_venv_modified": False,
    }
    if not resources["may_stage"]:
        return out
    expected = runner_temp / "myai-voice-staging" / "bin" / "python"
    report = runner_temp / "myai-voice-wheel-report" / "stt-wheel-report.json"
    if (
        not sandbox_python.is_file()
        or sandbox_python != expected
        or not inspect_resolve_report(report)["report_generated"]
    ):
        out["status"] = "reject-unverified-wheel-or-venv"
        return out
    env = os.environ.copy()
    env.update({
        "PIP_NO_INPUT": "1",
        "PIP_NO_CACHE_DIR": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "XDG_CACHE_HOME": str(runner_temp / "myai-voice-staging" / "cache"),
    })
    result = result_of_command(
        [str(sandbox_python), "-m", "pip", "install",
         "--only-binary=:all:", "--no-cache-dir", "--no-input",
         "--retries", "1", "--timeout", "15", "--progress-bar", "off",
         *STT_WHEELS],
        cwd=runner_temp, timeout=STT_PIP_TIMEOUT, env=env,
    )
    out["stt_wheel_packages_installed_in_temp_only"] = bool(result["exit_zero"])
    if not result["exit_zero"]:
        out["status"] = "stt-wheels-install-in-temp-failed"
        return out
    if (mem_available_kib() or 0) < 1536 * 1024:
        out["status"] = "no-go-ram-below-reserve-after-wheels"
        return out
    imports = import_probe_command(sandbox_python, runner_temp, env)
    out["import_probe"] = imports
    out["stt_python_imports_verified"] = bool(imports["imports_ok"])
    if imports["imports_ok"]:
        out["stt_import_peak_rss_mib"] = imports["peak_rss_mib"]
        out["status"] = "stt-package-imports-verified-without-model"
    else:
        out["status"] = "stt-optional-import-dependency-unavailable"
    return out


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, required=True)
    args = parser.parse_args()
    report = stage_stt_import(
        args.runner_temp / "myai-voice-staging" / "bin" / "python",
        args.runner_temp,
    )
    print("Isolated faster-whisper/CTranslate2 import and RSS:",
          json.dumps(report, sort_keys=True))
    print("No WhisperModel, model weights, microphone or GenieX action.")
    return 0 if report["stt_python_imports_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
