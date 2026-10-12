"""Resolve faster-whisper ARM64 wheels without installing models or packages.

Runs only after resource gating and an already created disposable voice venv.
pip install --dry-run --ignore-installed --only-binary=:all: --report checks
the full Python wheel dependency chain; nothing is installed, imported, or
cached. STT model weights and GenieX remain entirely untouched.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scripts.ventuno_voice_wheel_staging import (
    STT_WHEELS, STT_TIMEOUT_SECONDS, disk_free_bytes,
    mem_available_kib, preflight, result_of_command,
)


def inspect_resolve_report(path: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "report_generated": False,
        "candidate_package_count": 0,
        "key_wheel_versions": {},
    }
    if path.is_symlink() or not path.is_file():
        return report
    try:
        if not 0 < path.stat().st_size < 3_000_000:
            return report
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return report
    candidates = doc.get("install", []) if isinstance(doc, dict) else []
    if not isinstance(candidates, list) or len(candidates) > 80:
        return report
    versions = {}
    allow = {"faster-whisper", "ctranslate2", "av", "tokenizers",
             "huggingface-hub", "onnxruntime", "numpy"}
    for item in candidates:
        meta = item.get("metadata", {}) if isinstance(item, dict) else {}
        if not isinstance(meta, dict):
            return report
        name = str(meta.get("name", "")).lower().replace("_", "-")
        version = str(meta.get("version", ""))
        if name in allow and len(version) <= 35 and version.replace(".", "").replace("+", "").replace("-", "").isalnum():
            versions[name] = version
    report["report_generated"] = True
    report["candidate_package_count"] = len(candidates)
    report["key_wheel_versions"] = versions
    return report


def dry_run(sandbox_python: Path, runner_temp: Path, *, arm: bool = True
            ) -> dict[str, object]:
    resource = preflight(
        mem_available_kib(), disk_free_bytes(runner_temp), on_arm=arm
    )
    out: dict[str, object] = {
        **resource,
        "status": "no-go-stt-wheel-resolution",
        "wheel_resolution_succeeded": False,
        "faster_whisper_installed": False,
        "stt_model_weights_downloaded": False,
        "geniex_service_changed": False,
        "output_report": None,
    }
    if not resource["may_stage"]:
        return out
    expected = runner_temp / "myai-voice-staging" / "bin" / "python"
    if (
        not sandbox_python.is_file()
        or sandbox_python.is_symlink()
        or sandbox_python != expected
        or not runner_temp.is_dir()
        or runner_temp.is_symlink()
    ):
        out["status"] = "reject-non-isolated-python"
        return out
    report_folder = runner_temp / "myai-voice-wheel-report"
    if report_folder.exists() or report_folder.is_symlink():
        out["status"] = "reject-existing-report-folder"
        return out
    report_folder.mkdir(mode=0o700)
    output = report_folder / "stt-wheel-report.json"
    env = os.environ.copy()
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PIP_NO_INPUT"] = "1"
    env["PIP_NO_CACHE_DIR"] = "1"
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    job = result_of_command(
        [str(sandbox_python), "-m", "pip", "install",
         "--dry-run", "--ignore-installed", "--only-binary=:all:",
         "--no-cache-dir", "--no-input", "--retries", "1",
         "--timeout", "12", "--progress-bar", "off",
         "--report", str(output), *STT_WHEELS],
        timeout=STT_TIMEOUT_SECONDS, cwd=runner_temp, env=env,
    )
    result = inspect_resolve_report(output)
    out.update(result)
    if job["exit_zero"] and result["report_generated"]:
        out["status"] = "faster-whisper-arm64-wheels-resolved-no-install"
        out["wheel_resolution_succeeded"] = True
    else:
        out["status"] = "faster-whisper-wheel-resolution-inconclusive"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, required=True)
    args = parser.parse_args()
    result = dry_run(
        args.runner_temp / "myai-voice-staging" / "bin" / "python",
        args.runner_temp,
        arm=os.uname().machine.lower() in ("aarch64", "arm64"),
    )
    print("VENTUNO faster-whisper wheel compatibility:",
          json.dumps(result, sort_keys=True))
    print("Dependency resolution only. No STT model loaded, microphone used or service changed.")
    return 0 if result["wheel_resolution_succeeded"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
