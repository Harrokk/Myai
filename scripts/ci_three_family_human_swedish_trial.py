"""Exploratory three-family HUMAN Swedish ASR evidence, hosted ARM64 only.

All model bytes and public FLEURS dataset are pinned and checked before use.
This runs existing isolated STT backends without voice tool registration,
permission issuance or deployment. Never print individual transcripts/audio.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from core.voice_candidate_hosted_releases import hosted_model_release
from core.voice_candidate_native import IsolatedPinnedNativeCandidateSTT
from core.voice_candidate_preflight import verify_independent_candidates
from core.voice_parakeet_isolated import IsolatedPinnedParakeetSTT
from core.voice_verification import verify_tiered_transcripts
from scripts.ci_native_model_swedish_trial import word_error_count
from scripts.ci_swedish_fleurs_parakeet_trial import (
    FLEURS_BYTES, PARAKEET_FILES, SAMPLES, RSSSampler, decode_public_audio,
    nearest_rank, select_rows,
)

NATIVE_PROFILES = ("canary-1b-v2-q8", "whisper-small-q5_1")
EXPECTED_FAMILIES = frozenset({"parakeet", "canary", "whisper"})
_PROFILE_TO_KEY = {
    "parakeet": "p",
    "canary": "c",
    "whisper": "w",
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _native_attestations(root):
    binaries = root / "myai-native-fullcli-bin"
    if not binaries.is_dir():
        raise ValueError("Missing exact ARM64 CLI build")
    binary_digests = {}
    for name in ("transcribe-cli", "whisper-cli"):
        executable = binaries / name
        if not executable.is_file():
            raise ValueError("Missing reviewed native CLI")
        binary_digests[name] = sha256_file(executable)
        executable.chmod(0o555)
    binaries.chmod(0o555)

    manifests = {}
    for profile in NATIVE_PROFILES:
        release = hosted_model_release(profile)
        name = "transcribe-cli" if release.family == "canary" else "whisper-cli"
        model_dir = root / "myai-pinned-model-files" / profile
        model_file = model_dir / release.filename
        if (not model_file.is_file() or model_file.stat().st_size != release.bytes
                or sha256_file(model_file) != release.sha256):
            raise ValueError("Untrusted native model bytes")
        manifests[profile] = {
            "model_root": model_dir,
            "model_sha256": release.sha256,
            "runtime_root": binaries,
            "runtime_sha256": binary_digests[name],
        }
    verified = verify_independent_candidates(manifests)
    if {v.family for v in verified} != {"canary", "whisper"}:
        raise ValueError("Native family attribution disagreement")
    return {v.family: (v, manifests[v.profile]) for v in verified}


def _model_provider(family, root, native):
    if family == "parakeet":
        model_dir = root / "myai-parakeet-v3-int8"
        hashes = {name: digest for name, (_, digest) in PARAKEET_FILES.items()}
        provider = IsolatedPinnedParakeetSTT(
            model_name=str(model_dir),
            trusted_model_file_hashes=hashes,
            timeout_seconds=120, num_threads=2,
            virtual_memory_mib=0, cpu_seconds=0,
        )
        attested = provider.prepare_verified_model()
        return provider, attested.revision
    bound, args = native[family]
    profile_name = bound.profile
    provider = IsolatedPinnedNativeCandidateSTT(
        profile=bound,
        model_sha256=args["model_sha256"],
        runtime_sha256=args["runtime_sha256"],
        timeout_seconds=180, threads=2, virtual_memory_mib=0, cpu_seconds=0,
    )
    return provider, bound.model_revision


def _summarize_metrics(family, observations, peak_kib):
    if not observations:
        raise ValueError("Missing model evidence")
    word_errors = sum(o["errors"] for o in observations)
    words = sum(o["words"] for o in observations)
    times = [o["latency"] for o in observations]
    if words <= 0:
        raise ValueError("Missing reference evidence")
    return {
        "family": family,
        "samples": len(observations),
        "reference_words": words,
        "word_edits": word_errors,
        "corpus_wer": round(word_errors / words, 4),
        "empty_transcripts": sum(not o["text"].strip() for o in observations),
        "median_wall_seconds": round(nearest_rank(times, 50), 2),
        "p95_wall_seconds": round(nearest_rank(times, 95), 2),
        "max_wall_seconds": round(max(times), 2),
        "sampled_python_and_descendant_peak_rss_mib": round(peak_kib / 1024, 1),
    }


def evaluate_three_models(root):
    dataset = root / "myai-fleurs-sv_se-test.parquet"
    if not dataset.is_file() or dataset.stat().st_size != FLEURS_BYTES:
        raise ValueError("FLEURS pinned test file missing")
    native = _native_attestations(root)
    samples = [
        (decode_public_audio(encoded), reference)
        for encoded, reference in select_rows(dataset, limit=SAMPLES)
    ]
    if len(samples) != SAMPLES:
        raise ValueError("Models cannot compare unequal sample sets")
    by_family = {}
    trust = {}
    summaries = {}
    for family in ("parakeet", "canary", "whisper"):
        provider, revision = _model_provider(family, root, native)
        trust[_PROFILE_TO_KEY[family]] = {
            "family": family, "revision": revision,
        }
        observed = []
        try:
            with RSSSampler() as sampler:
                for pcm, reference in samples:
                    started = time.monotonic()
                    outcome = provider.transcribe(pcm)
                    duration = time.monotonic() - started
                    if type(outcome) is not dict or type(outcome.get("text")) is not str:
                        raise RuntimeError("Invalid provider response")
                    edit, count = word_error_count(reference, outcome["text"])
                    if count <= 0:
                        raise RuntimeError("Empty public reference text")
                    observed.append({
                        "text": outcome["text"], "errors": edit,
                        "words": count, "latency": duration,
                    })
                peak = sampler.peak_kib
        finally:
            provider.close()
        by_family[family] = observed
        summaries[family] = _summarize_metrics(family, observed, peak)

    if set(by_family) != EXPECTED_FAMILIES:
        raise ValueError("Three trusted family results required")
    accepted = 0
    critical_conflicts = 0
    abstentions = 0
    for i in range(SAMPLES):
        votes = [
            {"model_key": _PROFILE_TO_KEY[f], "text": by_family[f][i]["text"]}
            for f in ("parakeet", "canary", "whisper")
        ]
        result = verify_tiered_transcripts("critical", votes, trust)
        accepted += bool(result["accepted"])
        if result["reason"] in ("potentially_material_conflict", "no_exact_majority"):
            critical_conflicts += 1
        abstentions += any(not value["text"].strip() for value in
                           (by_family[f][i] for f in by_family))
    return {
        "hosted_arm64": True,
        "human_recorded_public_swedish": True,
        "dataset": "google/fleurs/sv_se/test",
        "pinned_dataset_and_three_family_model_weights": True,
        "samples_same_for_all_families": SAMPLES,
        "total_audio_seconds": round(sum(len(pcm) / 32000 for pcm, _ in samples), 2),
        "models": summaries,
        "critical_text_consensus_accepted_nonexecuting": accepted,
        "critical_text_consensus_denied_nonexecuting": SAMPLES - accepted,
        "explicit_nonempty_conflict_cases": critical_conflicts,
        "any_model_abstained": abstentions,
        "voice_tools_executed": False,
        "representative_accuracy": False,
        "independent_error_statistics_proven": False,
        "quality_gate_passed": False,
        "ventuno_or_geniex_concurrency_measured": False,
    }


def main(argv):
    if (len(argv) != 1 or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.uname().machine != "aarch64"):
        return 2
    try:
        root = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
        result = evaluate_three_models(root)
        print("HOSTED_THREE_FAMILY_HUMAN_SWEDISH " +
              json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print("HOSTED_THREE_FAMILY_HUMAN_SWEDISH: DENIED", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))
