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
from core.voice_verification import _canonical, verify_tiered_transcripts
from scripts.ci_native_model_swedish_trial import word_error_count
from scripts.ci_swedish_fleurs_parakeet_trial import (
    FLEURS_BYTES, PARAKEET_FILES, RSSSampler, decode_public_audio,
    nearest_rank, select_rows,
)

NATIVE_PROFILES = ("canary-1b-v2-q8", "whisper-small-q5_1")
EXPECTED_FAMILIES = frozenset({"parakeet", "canary", "whisper"})
THREE_FAMILY_SAMPLES = 36
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



def paired_exact_agreement(by_family, references):
    """Privacy-safe aggregate exact comparisons; NEVER permission evidence."""
    families = ("parakeet", "canary", "whisper")
    if (type(by_family) is not dict or set(by_family) != set(families)
            or type(references) not in (list, tuple) or not references
            or any(type(by_family[f]) is not list
                   or len(by_family[f]) != len(references) for f in families)):
        raise ValueError("Invalid paired model evidence")
    keys = (("parakeet", "canary"), ("parakeet", "whisper"),
            ("canary", "whisper"))
    pair_stats = {
        a + "_vs_" + b: {
            "exact_agreement": 0,
            "correct_exact_agreement": 0,
            "same_wrong_agreement": 0,
            "both_differ_from_reference": 0,
        } for a, b in keys
    }
    reference_matches = {f: 0 for f in families}
    three_correct = 0
    three_wrong = 0
    for index, reference in enumerate(references):
        canonical_reference = _canonical(reference)
        if not canonical_reference:
            raise ValueError("Invalid paired reference")
        transcripts = {}
        for f in families:
            record = by_family[f][index]
            if type(record) is not dict or type(record.get("text")) is not str:
                raise ValueError("Invalid model observation")
            text = _canonical(record["text"])
            if text is None:
                raise ValueError("Unbounded model transcript")
            transcripts[f] = text
            reference_matches[f] += int(bool(text) and text == canonical_reference)
        for left, right in keys:
            a, b = transcripts[left], transcripts[right]
            stat = pair_stats[left + "_vs_" + right]
            stat["both_differ_from_reference"] += int(
                a != canonical_reference and b != canonical_reference
            )
            if a and a == b:
                stat["exact_agreement"] += 1
                stat["correct_exact_agreement"] += int(a == canonical_reference)
                stat["same_wrong_agreement"] += int(a != canonical_reference)
        values = tuple(transcripts[f] for f in families)
        if values[0] and len(set(values)) == 1:
            three_correct += int(values[0] == canonical_reference)
            three_wrong += int(values[0] != canonical_reference)
    return {
        "samples": len(references),
        "per_family_exact_reference_matches": reference_matches,
        "pairwise_counts": pair_stats,
        "three_same_correct": three_correct,
        "three_same_wrong": three_wrong,
        "wrong_agreement_is_never_authorization": True,
    }


def evaluate_three_models(root):
    dataset = root / "myai-fleurs-sv_se-test.parquet"
    if not dataset.is_file() or dataset.stat().st_size != FLEURS_BYTES:
        raise ValueError("FLEURS pinned test file missing")
    native = _native_attestations(root)
    samples = [
        (decode_public_audio(encoded), reference)
        for encoded, reference in select_rows(dataset, limit=THREE_FAMILY_SAMPLES)
    ]
    if len(samples) != THREE_FAMILY_SAMPLES:
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
    for i in range(THREE_FAMILY_SAMPLES):
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
        "samples_same_for_all_families": THREE_FAMILY_SAMPLES,
        "total_audio_seconds": round(sum(len(pcm) / 32000 for pcm, _ in samples), 2),
        "models": summaries,
        "paired_exact_agreement": paired_exact_agreement(by_family, [reference for _, reference in samples]),
        "critical_text_consensus_accepted_nonexecuting": accepted,
        "critical_text_consensus_denied_nonexecuting": THREE_FAMILY_SAMPLES - accepted,
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
