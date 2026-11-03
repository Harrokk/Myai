"""Model-backed hosted-only Swedish speech smoke test (no private recordings).

Two open-source, pinned models are downloaded to a disposable GitHub-hosted
ARM64 worker, checked against expected exact file SHA256 and byte size, and
decoded via the reviewed isolated MyAI native child. This is a synthetic TTS
smoke test, NOT a statistically valid Swedish WER benchmark, and NEVER
authorizes tool use or production enablement.

All model/audio files stay under RUNNER_TEMP; no model weights or speech
recordings are uploaded as artifacts. Only summary diagnostics are printed.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import unicodedata
import wave

from core.voice_candidate_hosted_manifest import validate_hosted_manifest
from core.voice_candidate_preflight import verify_candidate_profile
from core.voice_candidate_native import IsolatedPinnedNativeCandidateSTT


PHRASES = (
    ("stäng inte av lampan", "negation"),
    ("hur mycket minne använder datorn", "read_only"),
)


def require_hosted_runner():
    if (os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.uname().machine != "aarch64"):
        raise RuntimeError("Model-backed experiment requires disposable hosted ARM64")
    root = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("Invalid disposable runner workspace")
    return root


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_downloaded_artifact(artifact, path):
    artifact.validate()
    p = Path(path)
    if (not p.is_file() or p.is_symlink()
            or p.name != artifact.filename
            or p.stat().st_size != artifact.byte_size
            or file_sha256(p) != artifact.sha256):
        raise ValueError("Hosted model SHA256 or expected size mismatch")
    return True


def make_synthetic_swedish_pcm(root, text, index):
    """Known public text only, synthesized by espeak-ng and ffmpeg on runner."""
    if text not in dict(PHRASES):
        raise ValueError("Unreviewed synthetic speech phrase")
    voice = root / f"synthetic-sv-{index}-native.wav"
    converted = root / f"synthetic-sv-{index}-pcm16.wav"
    subprocess.run(
        ["espeak-ng", "-v", "sv", "-s", "132", "-w", str(voice), text],
        timeout=20, check=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
         "-y", "-i", str(voice), "-ac", "1", "-ar", "16000",
         "-acodec", "pcm_s16le", str(converted)],
        timeout=25, check=True, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with wave.open(str(converted), "rb") as reader:
        if (reader.getnchannels() != 1
                or reader.getframerate() != 16000
                or reader.getsampwidth() != 2
                or not 0 < reader.getnframes() <= 30 * 16000):
            raise RuntimeError("Invalid synthetic Swedish audio format")
        data = reader.readframes(reader.getnframes())
    if not data or len(data) % 2:
        raise RuntimeError("Invalid synthetic PCM")
    voice.unlink(missing_ok=True)
    converted.unlink(missing_ok=True)
    return data


def norm_tokens(text):
    s = unicodedata.normalize("NFKC", text).casefold()
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in s)
    return s.split()


def word_error_rate(expected, recognized):
    a, b = norm_tokens(expected), norm_tokens(recognized)
    if not a:
        raise ValueError("Empty reference")
    previous = list(range(len(b) + 1))
    for i, aa in enumerate(a, 1):
        current = [i]
        for j, bb in enumerate(b, 1):
            current.append(min(
                current[j-1] + 1,
                previous[j] + 1,
                previous[j-1] + (aa != bb),
            ))
        previous = current
    return round(previous[-1] / len(a), 3)


def run_hosted_bench(root):
    artifacts = validate_hosted_manifest()
    weights = root / "myai-native-model-files"
    binaries = root / "myai-native-fullcli-bin"
    if not binaries.is_dir() or not weights.is_dir():
        raise RuntimeError("Reviewed native CLI and weights are required")
    speech = [make_synthetic_swedish_pcm(root, phrase, i)
              for i, (phrase, _) in enumerate(PHRASES)]
    report = {
        "scope": "hosted_arm64_synthetic_swedish_tts_not_real_wer",
        "models": [],
        "utterances": len(speech),
    }
    for artifact in artifacts:
        # Public, fixed model identifier only; no audio or transcript data.
        print("HOSTED_SV_MODEL_STAGE " + artifact.profile + " preflight",
              flush=True)
        directory = weights / artifact.profile
        model_file = directory / artifact.filename
        verify_downloaded_artifact(artifact, model_file)
        binary_filename = ("transcribe-cli" if artifact.profile ==
                           "canary-1b-v2-q8" else "whisper-cli")
        binary = binaries / binary_filename
        if not binary.is_file() or binary.is_symlink():
            raise RuntimeError("Reviewed ARM64 native binary missing")
        # The GitHub CI build is pinned to upstream source; this runtime
        # fingerprint is observed, not an independently signed binary.
        native_sha = file_sha256(binary)
        began = time.monotonic()
        profile = verify_candidate_profile(
            artifact.profile, model_root=str(directory),
            model_sha256=artifact.sha256,
            runtime_root=str(binaries), runtime_sha256=native_sha,
        )
        engine = IsolatedPinnedNativeCandidateSTT(
            profile=profile,
            model_sha256=artifact.sha256,
            runtime_sha256=native_sha,
            timeout_seconds=150, cpu_seconds=175,
            virtual_memory_mib=0, threads=2,
        )
        preflight_ms = int((time.monotonic() - began) * 1000)
        samples = []
        for (phrase, label), pcm in zip(PHRASES, speech):
            print("HOSTED_SV_MODEL_STAGE " + artifact.profile +
                  " decoding_" + label, flush=True)
            began = time.monotonic()
            before_rss_kib = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            result = engine.transcribe(pcm)
            ms = int((time.monotonic() - began) * 1000)
            after_rss_kib = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            if (type(result) is not dict or type(result.get("text")) is not str
                    or result.get("language") != "sv"
                    or not result["text"].strip()):
                raise RuntimeError("Native model returned invalid transcription")
            samples.append({
                "label": label,
                "latency_ms": ms,
                "wer_on_synthetic_tts_only": word_error_rate(
                    phrase, result["text"],
                ),
                "host_child_peak_rss_mib_upper_bound":
                    round(after_rss_kib / 1024, 1),
            })
            # A cumulative max RSS is not an exact per-model observation.
            # Do not report a misleading sample delta or Ventuno reading.
        engine.close()
        print("HOSTED_SV_MODEL_STAGE " + artifact.profile +
              " completed", flush=True)
        report["models"].append({
            "profile": artifact.profile,
            "preflight_ms": preflight_ms,
            "hosted_synthetic_samples": samples,
        })
    return report


def main():
    try:
        root = require_hosted_runner()
        report = run_hosted_bench(root)
        # No raw transcript, model contents or private paths are logged.
        print("HOSTED_SYNTHETIC_SWEDISH_STT_SMOKE: PASS")
        print(json.dumps(report, sort_keys=True, ensure_ascii=False))
        return 0
    except Exception as exc:
        # Only messages chosen from source-controlled safe error literals.
        # Do not print exception tracebacks, actual native output or paths.
        allow = {
            "Native candidate failed or returned no data": "native_nonzero_exit",
            "Native candidate output invalid": "native_stdout_schema",
            "Native candidate stdout exceeded limit": "stdout_bound",
            "Native candidate startup failed": "child_start_failure",
            "Native candidate failed": "child_runtime_failure",
            "Native candidate deadline exceeded": "native_deadline",
            "Native candidate reply revoked": "post_decode_revocation",
            "Native candidate identity changed or stopped": "identity_revoked",
            "Native candidate stopped": "stopped",
            "Native candidate model changed": "model_changed",
        }
        reason = allow.get(str(exc), "other")
        prefix = "Native candidate output invalid ("
        if (str(exc).startswith(prefix) and str(exc).endswith(")")):
            detail = str(exc)[len(prefix):-1]
            if detail in {
                "canary_status", "canary_empty", "canary_incomplete",
                "canary_language", "whisper_json", "whisper_schema",
                "whisper_segment", "whisper_duplicate", "unsafe_transcript",
                "unsafe_stdout", "utf8", "invalid_result", "other",
            }:
                reason = "native_stdout_" + detail
        print("HOSTED_SYNTHETIC_SWEDISH_STT_SMOKE: DENIED code=" +
              reason + " class=" + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
