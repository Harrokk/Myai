"""HOSTED-ONLY Swedish ASR trial with real, independently SHA-pinned weights.

Uses *synthetic Swedish text-to-speech* generated on a disposable ARM64
GitHub runner, not a person's voice. This is a functional smoke and a
single-phrase sanity check, NOT unbiased Swedish WER or VENTUNO readiness.
No tools/assistant/GenieX or network calls during native inference.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import wave

from core.voice_candidate_hosted_releases import hosted_model_release
from core.voice_candidate_native import IsolatedPinnedNativeCandidateSTT
from core.voice_candidate_preflight import verify_candidate_profile
import core.voice_candidate_native as native


_REFERENCE = "I dag är vädret fint i Stockholm."
_MAX_SYNTH_WAV = 1_000_000


def synthetic_swedish_pcm():
    """No uploaded audio or recorded humans; all generated WAV is in pipes."""
    generated = subprocess.run(
        ["espeak-ng", "-v", "sv", "-s", "125", "--stdout", _REFERENCE],
        capture_output=True, timeout=15, check=False,
    )
    if generated.returncode != 0 or not 0 < len(generated.stdout) <= _MAX_SYNTH_WAV:
        raise RuntimeError("No controlled Swedish TTS")
    converted = subprocess.run(
        ["sox", "-t", "wav", "-", "-r", "16000", "-c", "1",
         "-b", "16", "-e", "signed-integer", "-t", "wav", "-"],
        input=generated.stdout, capture_output=True, timeout=15, check=False,
    )
    if converted.returncode != 0 or not 44 < len(converted.stdout) <= _MAX_SYNTH_WAV:
        raise RuntimeError("Could not convert synthetic WAV")
    with wave.open(io.BytesIO(converted.stdout), "rb") as wav:
        if (wav.getframerate() != 16000 or wav.getsampwidth() != 2
                or wav.getnchannels() != 1 or wav.getcomptype() != "NONE"):
            raise RuntimeError("Invalid synthetic Swedish audio format")
        frames = wav.readframes(wav.getnframes())
    if not 0 < len(frames) <= 960_000 or len(frames) % 2:
        raise RuntimeError("Synthetic Swedish audio exceeds cap")
    return frames


def words(text):
    return re.findall(r"[a-zåäö0-9]+", text.casefold())


def word_error_count(reference, hypothesis):
    a, b = words(reference), words(hypothesis)
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(
                current[-1] + 1, previous[j] + 1,
                previous[j - 1] + (x != y),
            ))
        previous = current
    return previous[-1], len(a)


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def measured_model_trial(profile_name, runner_temp):
    release = hosted_model_release(profile_name)
    root = Path(runner_temp).resolve(strict=True)
    model_root = root / "myai-pinned-model-files" / profile_name
    bin_root = root / "myai-native-fullcli-bin"
    binary_name = ("transcribe-cli" if release.family == "canary"
                   else "whisper-cli")
    model_path = model_root / release.filename
    native_path = bin_root / binary_name
    if (not model_path.is_file() or not native_path.is_file()
            or model_path.stat().st_size != release.bytes
            or sha256_file(model_path) != release.sha256):
        raise ValueError("Pinned model hash was not verified")
    # No hashes are taken from native stdout or from the LLM.
    runtime_sha256 = sha256_file(native_path)
    native_path.chmod(0o555)
    bin_root.chmod(0o555)

    bound = verify_candidate_profile(
        profile_name,
        model_root=model_root,
        model_sha256=release.sha256,
        runtime_root=bin_root,
        runtime_sha256=runtime_sha256,
    )
    provider = IsolatedPinnedNativeCandidateSTT(
        profile=bound,
        model_sha256=release.sha256,
        runtime_sha256=runtime_sha256,
        timeout_seconds=180,
        threads=2,
        # No guessed RLIMIT_AS cap: actual VM/RSS must first be observed.
        virtual_memory_mib=0, cpu_seconds=0,
    )
    pcm = synthetic_swedish_pcm()
    observed = {"rss_kib": 0}
    finished = threading.Event()
    samples = []

    original_launch = native._launch_native_candidate_worker

    def instrumented_launch(args, **kwargs):
        proc = original_launch(args, **kwargs)
        def sampler():
            while not finished.is_set():
                try:
                    # Samples only main native PID; not an aggregate cgroup RSS.
                    lines = Path("/proc/" + str(proc.pid) + "/status").read_text()
                    for line in lines.splitlines():
                        if line.startswith("VmRSS:"):
                            observed["rss_kib"] = max(
                                observed["rss_kib"], int(line.split()[1]),
                            )
                            break
                except (OSError, ValueError, IndexError):
                    pass
                time.sleep(0.05)
        task = threading.Thread(target=sampler, daemon=True)
        samples.append(task)
        task.start()
        return proc

    native._launch_native_candidate_worker = instrumented_launch
    started = time.monotonic()
    try:
        result = provider.transcribe(pcm)
    finally:
        native._launch_native_candidate_worker = original_launch
        finished.set()
        for task in samples:
            task.join(timeout=2)
        provider.close()
    latency = time.monotonic() - started
    if type(result) is not dict or not words(result.get("text", "")):
        raise RuntimeError("Actual native ASR did not produce Swedish text")
    errors, count = word_error_count(_REFERENCE, result["text"])
    summary = {
        "family": release.family,
        "profile": release.profile,
        "synthetic_swedish_tts": True,
        "model_source_sha256_verified": True,
        "native_sha256_verified": True,
        "audio_duration_seconds": round(len(pcm) / 32000, 2),
        "wall_seconds": round(latency, 2),
        "sampled_main_pid_peak_rss_mib": (
            round(observed["rss_kib"] / 1024, 1)
            if observed["rss_kib"] else None
        ),
        "phrase_reference_words": count,
        "phrase_levenshtein_errors": errors,
        "speech_quality_is_statistically_representative": False,
    }
    return summary


def main(argv):
    if (len(argv) != 2
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.uname().machine != "aarch64"):
        return 2
    try:
        summary = measured_model_trial(
            argv[1], os.environ["RUNNER_TEMP"],
        )
        print("HOSTED_SYNTHETIC_SWEDISH_MODEL_TRIAL " +
              json.dumps(summary, sort_keys=True))
        return 0
    except Exception:
        # No CLI stdout, audio, downloaded URL, private paths or tokens.
        print("HOSTED_SYNTHETIC_SWEDISH_MODEL_TRIAL: DENIED", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))
