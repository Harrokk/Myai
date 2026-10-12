"""Gated ARM64 Whisper Tiny Swedish CPU smoke, temporary artifacts only.

Exactly one pinned MIT-licensed multilingual Systran/faster-whisper-tiny model;
never the English-only model, microphone, user audio, VENTUNO NPU or GenieX
API. 2 seconds of synthesized digital silence test model load/inference, NOT
Swedish word accuracy. Uses the staging venv and runner temp, 8 GiB RAM gate,
3 GiB disk gate, restricted process CPU and virtual memory, bounded time,
and discards the model/cache in the calling workflow's always() cleanup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

from scripts.ventuno_voice_wheel_staging import disk_free_bytes, mem_available_kib
from scripts.ventuno_swedish_reference_audio import validate_swedish_sample

REPO = "Systran/faster-whisper-tiny"
REVISION = "d90ca5fe260221311c53c58e660288d3deb8d356"
EXPECTED_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
MODEL_BIN_MIN = 60_000_000
MODEL_BIN_MAX = 90_000_000
MAX_MODEL_SUM_BYTES = 105_000_000
MIN_MEM_AVAILABLE_KIB = 8 * 1024 * 1024
MIN_DISK_AVAILABLE_BYTES = 3 * 1024**3
DOWNLOAD_TIMEOUT_SECONDS = 180
INFERENCE_TIMEOUT_SECONDS = 175
MAX_AS_BYTES = 5 * 1024**3
MAX_CPU_SECONDS = 115

_DOWNLOAD = r"""
import json
import os
from pathlib import Path
from huggingface_hub import snapshot_download

folder = Path(os.environ["MYAI_TINY_MODEL_DIR"])
result = snapshot_download(
    repo_id="Systran/faster-whisper-tiny",
    revision="d90ca5fe260221311c53c58e660288d3deb8d356",
    allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"],
    local_dir=str(folder),
    max_workers=2,
    token=False,
)
assert Path(result).resolve() == folder.resolve()
print(json.dumps({"download_complete": True}))
"""

_RUN = r"""
import json
import os
import resource
import time
import numpy as np
from faster_whisper import WhisperModel

start=time.monotonic()
model=WhisperModel(
    os.environ["MYAI_TINY_MODEL_DIR"],
    device="cpu", compute_type="int8",
    cpu_threads=2, num_workers=1, local_files_only=True,
)
loaded=time.monotonic()
# Synthetic two-second digital silence (NOT a spoken Swedish test sentence).
audio=np.zeros(2*16000, dtype=np.float32)
segments, info=model.transcribe(
    audio, language="sv", task="transcribe",
    beam_size=1, best_of=1, condition_on_previous_text=False,
    vad_filter=False, without_timestamps=True,
    no_speech_threshold=0.6,
)
results=list(segments)
finish=time.monotonic()
speech_attempted=False
speech_word_match=False
speech_decode_seconds=None
speech_segment_count=None
source=os.environ.get("MYAI_SWEDISH_OGG_PATH")
if source:
    speech_attempted=True
    audio_start=time.monotonic()
    speech, audio_info=model.transcribe(
        source, language="sv", task="transcribe",
        beam_size=1, best_of=1, condition_on_previous_text=False,
        vad_filter=False, without_timestamps=True,
        no_speech_threshold=0.6,
    )
    words=list(speech)
    speech_decode_seconds=round(time.monotonic()-audio_start,3)
    speech_segment_count=len(words)
    # Public fixture content only; recognized words are not logged.
    normalized=" ".join(seg.text for seg in words).lower()
    speech_word_match="svenska" in normalized
# No recognized text, user speech or model path is logged.
print(json.dumps({
    "model_load_seconds": round(loaded-start,3),
    "two_second_silence_inference_seconds": round(finish-loaded,3),
    "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
    "language_requested": "sv",
    "segments_returned": len(results),
    "speech_accuracy_tested": False,
    "swedish_public_word_attempted": speech_attempted,
    "swedish_public_word_recognized": speech_word_match,
    "swedish_public_word_inference_seconds": speech_decode_seconds,
    "swedish_public_word_segments": speech_segment_count,
    "microphone_used": False,
    "npu_used": False,
    "model_created_on_cpu": True,
}))
"""


def new_isolated_directory(path: Path, root: Path) -> bool:
    try:
        return (
            not path.exists() and not path.is_symlink()
            and not root.is_symlink() and root.is_dir()
            and path.parent.resolve() == root.resolve()
            and path.name == "myai-whisper-tiny-model"
        )
    except OSError:
        return False


def model_integrity(path: Path) -> dict[str, object]:
    out: dict[str, object] = {
        "model_metadata_complete": False,
        "model_binary_bytes": None,
        "model_sha256": None,
        "total_model_bytes": None,
    }
    if path.is_symlink() or not path.is_dir():
        return out
    sizes = {}
    for name in EXPECTED_FILES:
        item = path / name
        try:
            if item.is_symlink() or not item.is_file():
                return out
            sizes[name] = item.stat().st_size
        except OSError:
            return out
    if not MODEL_BIN_MIN <= sizes["model.bin"] <= MODEL_BIN_MAX:
        return out
    if not 0 < sizes["config.json"] <= 100_000:
        return out
    if not 0 < sizes["tokenizer.json"] <= 6_000_000:
        return out
    if not 0 < sizes["vocabulary.txt"] <= 2_000_000:
        return out
    if sum(sizes.values()) > MAX_MODEL_SUM_BYTES:
        return out
    try:
        meta = json.loads((path / "config.json").read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or len(meta) > 120:
            return out
        digest = hashlib.file_digest(
            (path / "model.bin").open("rb"), "sha256"
        ).hexdigest()
    except (OSError, ValueError, TypeError):
        return out
    out.update({
        "model_metadata_complete": True,
        "model_binary_bytes": sizes["model.bin"],
        "total_model_bytes": sum(sizes.values()),
        "model_sha256": digest,
    })
    return out


def run_restricted(python: Path, program: str,
                   root: Path, model: Path, *, timeout: int,
                   inference: bool, speech_path: Path | None = None) -> dict[str, object]:
    import resource
    env = os.environ.copy()
    env.update({
        "MYAI_TINY_MODEL_DIR": str(model),
        "HF_HOME": str(root / "myai-whisper-hf-cache"),
        "HF_HUB_CACHE": str(root / "myai-whisper-hf-cache" / "hub"),
        "XDG_CACHE_HOME": str(root / "myai-whisper-hf-cache"),
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    if speech_path is not None:
        env["MYAI_SWEDISH_OGG_PATH"] = str(speech_path)
    if inference:
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"

    def restrict():
        resource.setrlimit(resource.RLIMIT_AS, (MAX_AS_BYTES, MAX_AS_BYTES))
        resource.setrlimit(
            resource.RLIMIT_CPU, (MAX_CPU_SECONDS, MAX_CPU_SECONDS)
        )
    try:
        completed = subprocess.run(
            [str(python), "-I", "-c", program],
            env=env, cwd=root, capture_output=True, text=True,
            errors="replace", timeout=timeout, check=False,
            preexec_fn=restrict if inference else None,
        )
    except subprocess.TimeoutExpired:
        return {"succeeded": False, "reason": "timeout"}
    except OSError:
        return {"succeeded": False, "reason": "launch-error"}
    if completed.returncode:
        # Do not expose arbitrary stderr, paths, tokens or generated text.
        classification = re.findall(
            r"(?m)^(OSError|RuntimeError|ValueError|MemoryError|"
            r"ImportError|ModuleNotFoundError):",
            completed.stderr[-2000:],
        )
        return {
            "succeeded": False,
            "reason": classification[-1] if classification else "nonzero-exit",
            "exit_code": completed.returncode,
        }
    try:
        result = json.loads(completed.stdout.strip())
        if not isinstance(result, dict):
            raise ValueError
    except (ValueError, TypeError):
        return {"succeeded": False, "reason": "invalid-reported-result"}
    return {"succeeded": True, "result": result}


def smoke(sandbox_python: Path, root: Path,
          *, machine: str | None = None) -> dict[str, object]:
    arm = (machine or platform.machine()).lower() in ("aarch64", "arm64")
    memory = mem_available_kib()
    disk = disk_free_bytes(root)
    report: dict[str, object] = {
        "status": "no-go-whisper-tiny-benchmark",
        "arch_arm64": arm,
        "memory_available_mib": round(memory/1024) if memory else None,
        "free_disk_mib": round(disk/1024**2) if disk else None,
        "memory_budget_minimum_mib": MIN_MEM_AVAILABLE_KIB//1024,
        "model_id": REPO,
        "pinned_revision": REVISION,
        "model_files_verified": False,
        "cpu_inference_verified": False,
        "model_memory_peak_mib": None,
        "microphone_used": False,
        "language_accuracy_verified": False,
        "swedish_public_word_attempted": False,
        "swedish_public_word_recognized": None,
        "model_installed_in_production": False,
        "geniex_restarted": False,
    }
    if not arm or memory is None or memory < MIN_MEM_AVAILABLE_KIB or disk is None or disk < MIN_DISK_AVAILABLE_BYTES:
        return report
    expected_py = root / "myai-voice-staging" / "bin" / "python"
    folder = root / "myai-whisper-tiny-model"
    if (
        not sandbox_python.is_file() or sandbox_python != expected_py
        or not new_isolated_directory(folder, root)
        or (root / "myai-whisper-hf-cache").exists()
    ):
        report["status"] = "reject-non-isolated-or-existing-model-files"
        return report
    outcome = run_restricted(
        sandbox_python, _DOWNLOAD, root, folder,
        timeout=DOWNLOAD_TIMEOUT_SECONDS, inference=False,
    )
    if not outcome["succeeded"] or outcome["result"].get("download_complete") is not True:
        report["status"] = "model-download-unavailable"
        report["download_reason"] = outcome.get("reason")
        return report
    model = model_integrity(folder)
    report.update(model)
    report["model_files_verified"] = bool(model["model_metadata_complete"])
    if not report["model_files_verified"]:
        report["status"] = "model-file-size-or-metadata-rejected"
        return report
    if (mem_available_kib() or 0) < MIN_MEM_AVAILABLE_KIB:
        report["status"] = "no-go-memory-budget-after-download"
        return report
    sample = root / "myai-whisper-swedish-word.ogg"
    sample_path = None
    if sample.exists() or sample.is_symlink():
        if sample.is_symlink() or not sample.is_file():
            report["status"] = "reject-swedish-fixture-path"
            return report
        try:
            raw = sample.read_bytes() if sample.stat().st_size < 30_001 else b""
        except OSError:
            raw = b""
        if not validate_swedish_sample(raw):
            report["status"] = "reject-swedish-audio-integrity"
            return report
        sample_path = sample
    result = run_restricted(
        sandbox_python, _RUN, root, folder,
        timeout=INFERENCE_TIMEOUT_SECONDS, inference=True,
        speech_path=sample_path,
    )
    if not result["succeeded"]:
        report["status"] = "stt-cpu-inference-failed"
        report["inference_error"] = result.get("reason")
        return report
    measurements = result["result"]
    if not (
        measurements.get("model_created_on_cpu") is True
        and measurements.get("language_requested") == "sv"
        and measurements.get("microphone_used") is False
        and measurements.get("npu_used") is False
        and isinstance(measurements.get("peak_rss_mib"), (int, float))
        and 0 < measurements["peak_rss_mib"] < 4096
        and isinstance(measurements.get("two_second_silence_inference_seconds"), (int, float))
        and 0 <= measurements["two_second_silence_inference_seconds"] < INFERENCE_TIMEOUT_SECONDS
    ):
        report["status"] = "reject-invalid-cpu-inference-measurement"
        return report
    if sample_path is not None:
        if (
            measurements.get("swedish_public_word_attempted") is not True
            or type(measurements.get("swedish_public_word_recognized")) is not bool
        ):
            report["status"] = "reject-incomplete-swedish-word-measurement"
            return report
        report["swedish_public_word_attempted"] = True
        report["swedish_public_word_recognized"] = (
            measurements["swedish_public_word_recognized"]
        )
    report["cpu_inference_verified"] = True
    report["model_memory_peak_mib"] = measurements["peak_rss_mib"]
    report["cpu_measurements"] = measurements
    report["status"] = "tiny-sv-cpu-silence-inference-verified"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, required=True)
    args = parser.parse_args()
    report = smoke(
        args.runner_temp / "myai-voice-staging" / "bin" / "python",
        args.runner_temp,
    )
    print("VENTUNO isolated multilingual Whisper Tiny:",
          json.dumps(report, sort_keys=True))
    print("Two-second digital silence is NOT a Swedish transcription quality test.")
    return 0 if report["cpu_inference_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
