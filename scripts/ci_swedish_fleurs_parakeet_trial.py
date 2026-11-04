"""Explore real HUMAN Swedish ASR on disposable hosted ARM64, never on VENTUNO.

Public SHA-pinned Google FLEURS test split; pin and download in workflow.
No microphone, user recordings, tool execution or transcription logging.
"""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from core.voice_parakeet_isolated import IsolatedPinnedParakeetSTT
from core.voice_verification import _canonical
from scripts.ci_native_model_swedish_trial import word_error_count

FLEURS_REVISION = "14b46a200cec86ab4cf963c5c0b4661ef343f34a"
FLEURS_BYTES = 537731833
FLEURS_SHA256 = "efaddda3e8460662b26d07c9fa1e52cbf57fb18365acf5bc232ea1bcf43ed935"
PARAKEET_REVISION = "2bda32ec70b097a55adaa07d9a7173915b43cc78"
PARAKEET_FILES = {
    "encoder.int8.onnx": (652184281, "acfc2b4456377e15d04f0243af540b7fe7c992f8d898d751cf134c3a55fd2247"),
    "decoder.int8.onnx": (11845275, "179e50c43d1a9de79c8a24149a2f9bac6eb5981823f2a2ed88d655b24248db4e"),
    "joiner.int8.onnx": (6355277, "3164c13fc2821009440d20fcb5fdc78bff28b4db2f8d0f0b329101719c0948b3"),
    "tokens.txt": (93939, "d58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d"),
}
SAMPLES = 12
_MAX_ENCODED = 6_000_000
_MAX_PCM = 20 * 16000 * 2


def select_rows(parquet_file, limit=SAMPLES):
    if type(limit) is not int or not 1 <= limit <= 60:
        raise ValueError("Invalid sample count")
    import pyarrow.parquet as pq
    reader = pq.ParquetFile(str(parquet_file))
    if not {"audio", "transcription", "num_samples"}.issubset(reader.schema_arrow.names):
        raise ValueError("FLEURS file does not have the expected fields")
    found = 0
    for batch in reader.iter_batches(
        batch_size=4, columns=["audio", "transcription", "num_samples"]
    ):
        for row in batch.to_pylist():
            audio = row.get("audio")
            text = row.get("transcription")
            length = row.get("num_samples")
            if (not isinstance(audio, dict) or type(audio.get("bytes")) is not bytes
                    or not 32 <= len(audio["bytes"]) <= _MAX_ENCODED
                    or type(text) is not str or not text.strip()
                    or type(length) is not int or not 16000 <= length <= 320000):
                continue
            yield audio["bytes"], text
            found += 1
            if found == limit:
                return
    raise ValueError("Insufficient fixed bounded human audio samples")


def decode_public_audio(data):
    if type(data) is not bytes or not 32 <= len(data) <= _MAX_ENCODED:
        raise ValueError("Invalid public audio")
    try:
        p = subprocess.run(
            ["/usr/bin/ffmpeg", "-hide_banner", "-loglevel", "error",
             "-nostdin", "-threads", "1", "-i", "pipe:0",
             "-ac", "1", "-ar", "16000", "-f", "s16le",
             "-acodec", "pcm_s16le", "pipe:1"],
            input=data, capture_output=True, timeout=25, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Public audio decoding failed") from None
    if (p.returncode != 0 or not 0 < len(p.stdout) <= _MAX_PCM
            or len(p.stdout) % 2):
        raise RuntimeError("Invalid public PCM output")
    return p.stdout


def _rss_tree_kib(root_pid):
    """Instantaneous sampled process-tree RSS; NOT bounded cgroup memory."""
    seen = set()
    queue = [root_pid]
    total = 0
    while queue and len(seen) < 64:
        pid = queue.pop()
        if pid in seen:
            continue
        seen.add(pid)
        try:
            for line in Path("/proc/%d/status" % pid).read_text(encoding="ascii").splitlines():
                if line.startswith("VmRSS:"):
                    total += int(line.split()[1])
                    break
            children = Path("/proc/%d/task/%d/children" % (pid, pid))
            queue.extend(int(x) for x in children.read_text(encoding="ascii").split())
        except (OSError, IndexError, ValueError):
            pass
    return total


def nearest_rank(values, percent):
    if not values or not 0 < percent <= 100:
        raise ValueError("Missing latency evidence")
    seq = sorted(values)
    return seq[max(0, math.ceil(len(seq) * percent / 100) - 1)]


class RSSSampler:
    def __init__(self):
        self.stop = threading.Event()
        self.peak_kib = 0
        self.thread = None

    def __enter__(self):
        def run():
            while not self.stop.is_set():
                self.peak_kib = max(self.peak_kib, _rss_tree_kib(os.getpid()))
                self.stop.wait(0.05)
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=2)
        self.peak_kib = max(self.peak_kib, _rss_tree_kib(os.getpid()))


def evaluate(parquet, model_dir, limit=SAMPLES):
    hashes = {name: digest for name, (_, digest) in PARAKEET_FILES.items()}
    stt = IsolatedPinnedParakeetSTT(
        model_name=str(model_dir),
        trusted_model_file_hashes=hashes,
        timeout_seconds=120, num_threads=2,
        virtual_memory_mib=0, cpu_seconds=0,
    )
    word_edits = 0
    reference_words = 0
    wall_times = []
    empty = 0
    audio_seconds = 0.0
    count = 0
    try:
        stt.prepare_verified_model()
        with RSSSampler() as monitor:
            for encoded, reference in select_rows(parquet, limit=limit):
                pcm = decode_public_audio(encoded)
                start = time.monotonic()
                result = stt.transcribe(pcm)
                wall_times.append(time.monotonic() - start)
                if type(result) is not dict or type(result.get("text")) is not str:
                    raise RuntimeError("Untrusted STT reply")
                err, ref_words = word_error_count(reference, result["text"])
                if ref_words < 1:
                    raise RuntimeError("Invalid reference text")
                word_edits += err
                reference_words += ref_words
                empty += not bool(_canonical(result["text"]))
                audio_seconds += len(pcm) / 32000
                count += 1
            peak = monitor.peak_kib
        if count != limit:
            raise RuntimeError("Incomplete FLEURS sample set")
    finally:
        stt.close()
    return {
        "family": "parakeet",
        "profile": "parakeet-tdt-0.6b-v3-int8",
        "hosted_arm64": True,
        "human_recorded_public_swedish": True,
        "dataset": "google/fleurs/sv_se/test",
        "sha256_pinned_dataset_and_four_model_files": True,
        "samples": count,
        "reference_words": reference_words,
        "word_edits": word_edits,
        "corpus_wer": round(word_edits / reference_words, 4),
        "empty_transcripts": empty,
        "audio_seconds": round(audio_seconds, 2),
        "median_wall_seconds": round(nearest_rank(wall_times, 50), 2),
        "p95_wall_seconds": round(nearest_rank(wall_times, 95), 2),
        "max_wall_seconds": round(max(wall_times), 2),
        "sampled_python_and_descendant_peak_rss_mib": round(peak / 1024, 1),
        "representative_accuracy": False,
        "quality_gate_passed": False,
        "ventuno_measured": False,
    }


def main():
    if (os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or os.uname().machine != "aarch64"):
        return 2
    root = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    parquet = root / "myai-fleurs-sv_se-test.parquet"
    model = root / "myai-parakeet-v3-int8"
    try:
        if (not parquet.is_file() or parquet.stat().st_size != FLEURS_BYTES
                or not model.is_dir()
                or any(not (model / name).is_file()
                       or (model / name).stat().st_size != size
                       for name, (size, _) in PARAKEET_FILES.items())):
            raise RuntimeError("Model or dataset preflight failed")
        result = evaluate(parquet, model)
        print("HOSTED_HUMAN_SWEDISH_PARAKEET_TRIAL " +
              json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception:
        print("HOSTED_HUMAN_SWEDISH_PARAKEET_TRIAL: DENIED", file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
