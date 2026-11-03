"""CPU-only Parakeet v3 with a pinned GitHub release and public Swedish speech.

Only for a disposable GitHub-hosted ARM64 test workspace. Never accesses
microphones, production services, network endpoints except the already
integrity-checked public fixture downloader, or user/private audio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import resource
import tarfile
import time
from pathlib import Path

ARCHIVE_BYTES = 487_170_055
ARCHIVE_SHA256 = "5793d0fd397c5778d2cf2126994d58e9d56b1be7c04d13c7a15bb1b4eafb16bf"
MODEL_DIR_NAME = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8"
EXPECTED_FILES = {
    "encoder.int8.onnx": 800_000_000,
    "decoder.int8.onnx": 100_000_000,
    "joiner.int8.onnx": 100_000_000,
    "tokens.txt": 1_000_000,
}
MAX_PCM_BYTES = 16_000 * 2 * 12
SILERO_BYTES = 643_854
SILERO_SHA256 = '9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6'


class PublicVadIntegrationError(RuntimeError):
    def __init__(self, stage):
        self.stage = stage
        super().__init__(stage)


def verify_archive(path: Path) -> bool:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size != ARCHIVE_BYTES:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest() == ARCHIVE_SHA256
    except OSError:
        return False


def extract_required_files(archive: Path, target: Path) -> Path:
    """Extract only four exact model files; reject duplicate/link/oversize items."""
    if not target.parent.is_dir() or target.is_symlink() or target.exists():
        raise ValueError("Invalid destination for Parakeet model")
    target.mkdir(mode=0o700)
    found = set()
    with tarfile.open(archive, mode="r:bz2") as handle:
        for member in handle:
            parts = member.name.lstrip("./").split("/")
            if len(parts) != 2 or parts[0] != MODEL_DIR_NAME:
                continue
            filename = parts[1]
            if filename not in EXPECTED_FILES:
                continue
            if filename in found or not member.isfile() or not 0 < member.size <= EXPECTED_FILES[filename]:
                raise ValueError("Unexpected Parakeet archive member")
            inp = handle.extractfile(member)
            if inp is None:
                raise ValueError("Unreadable Parakeet archive member")
            remaining = member.size
            with (target / filename).open("xb") as dst:
                while remaining:
                    data = inp.read(min(1 << 20, remaining))
                    if not data:
                        raise ValueError("Incomplete Parakeet archive member")
                    dst.write(data)
                    remaining -= len(data)
            found.add(filename)
    if found != set(EXPECTED_FILES):
        raise ValueError("Parakeet archive missing required model files")
    return target


def public_ogg_to_pcm(source: Path) -> bytes:
    """Decode a *verified public* OGG fixture, never user audio."""
    try:
        import av
        chunks = []
        length = 0
        with av.open(str(source), mode="r") as container:
            if len(container.streams.audio) != 1:
                raise ValueError("Unexpected public reference audio streams")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            def collect(frame):
                nonlocal length
                raw = frame.to_ndarray().tobytes()
                length += len(raw)
                if length > MAX_PCM_BYTES:
                    raise ValueError("Public reference audio too long")
                chunks.append(raw)
            for frame in container.decode(container.streams.audio[0]):
                for converted in resampler.resample(frame):
                    collect(converted)
            for converted in resampler.resample(None):
                collect(converted)
        audio = b"".join(chunks)
    except Exception:
        raise RuntimeError("Public Swedish fixture decoder unavailable") from None
    if not 2_000 <= len(audio) <= MAX_PCM_BYTES or len(audio) % 2:
        raise ValueError("Public Swedish fixture PCM length invalid")
    return audio


def verified_silero_model(path: Path) -> bool:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size != SILERO_BYTES:
            return False
        with path.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest() == SILERO_SHA256
    except OSError:
        return False


def public_pcm_vad_segments(audio: bytes, model_path: Path) -> list[bytes]:
    """Return Silero-completed segments from public 20-ms PCM16 frames."""
    from modules.voice.sherpa_silero_segments import SherpaSileroSegments

    if not verified_silero_model(model_path):
        raise RuntimeError("Public Silero model hash mismatch")
    detector = SherpaSileroSegments(model_path=str(model_path))
    out = []
    for offset in range(0, len(audio), 640):
        frame = audio[offset:offset + 640]
        frame += bytes(640 - len(frame))
        out.extend(detector.feed(frame))
    out.extend(detector.flush())
    return out


def run(archive: Path, scratch: Path, silero_model: Path | None = None) -> dict[str, object]:
    from modules.voice.sherpa_onnx_provider import SherpaOnnxParakeetSTT
    from scripts.ventuno_swedish_reference_audio import download_fixture

    if scratch.is_symlink() or not scratch.is_dir():
        raise RuntimeError("Unsafe hosted test workspace")
    if not verify_archive(archive):
        raise RuntimeError("Parakeet archive size/hash verification failed")

    local = scratch / "parakeet-local-verified"
    files = extract_required_files(archive, local)

    fixture = download_fixture(scratch)
    if not fixture["sample_verified"]:
        raise RuntimeError("Public Swedish reference integrity verification failed")
    audio = public_ogg_to_pcm(scratch / "myai-whisper-swedish-word.ogg")

    stt = SherpaOnnxParakeetSTT(
        model_name=str(files), device="cpu", compute_type="int8",
        language="sv", num_threads=2,
    )
    begin = time.monotonic()
    stt._load_model()
    loaded = time.monotonic()
    silero_report = {"silero_tested": False, "silero_speech_segments": None,
                     "silero_swedish_word_recognized": None,
                     "silero_decode_seconds": None}
    try:
        result = stt.transcribe(audio)
        if silero_model is not None:
            vad_start = time.monotonic()
            try:
                segments = public_pcm_vad_segments(audio, silero_model)
            except Exception as error:
                raise PublicVadIntegrationError('silero-segment-' + type(error).__name__) from None
            silero_report["silero_tested"] = True
            silero_report["silero_speech_segments"] = len(segments)
            if segments:
                # Source fixture only, no new model or microphone.
                try:
                    recognized = stt.transcribe(segments[0])
                except Exception as error:
                    raise PublicVadIntegrationError('silero-stt-' + type(error).__name__) from None
                tokens = set(re.findall(r"[a-zåäö]+", recognized["text"].casefold()))
                silero_report["silero_swedish_word_recognized"] = "svenska" in tokens
            silero_report["silero_decode_seconds"] = round(
                time.monotonic() - vad_start, 3
            )
    finally:
        stt.release_for_inference()
    ended = time.monotonic()

    # The only fixture is public; still output only classification/metrics.
    words = set(re.findall(r"[a-zåäö]+", result["text"].casefold()))
    return {
        **silero_report,
        "status": "public-swedish-word-recognized" if "svenska" in words
                  else "public-swedish-word-not-recognized",
        "swedish_word_recognized": "svenska" in words,
        "model_archive_sha256_verified": True,
        "model_load_seconds": round(loaded - begin, 3),
        "decode_seconds": round(ended - loaded, 3),
        "public_audio_seconds": round(len(audio) / 32000, 3),
        "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "microphone_used": False,
        "user_audio_used": False,
        "npu_used": False,
        "production_services_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--runner-temp", required=True, type=Path)
    parser.add_argument("--silero-model", type=Path)
    args = parser.parse_args()
    try:
        report = run(args.archive, args.runner_temp, args.silero_model)
    except Exception as error:
        # Avoid native error strings, which may disclose paths or input content.
        print(json.dumps({"status": "no-go-public-parakeet-inference",
                          "error_type": type(error).__name__,
                          "error_stage": error.stage if isinstance(error, PublicVadIntegrationError) else "other",
                          "microphone_used": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["swedish_word_recognized"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
