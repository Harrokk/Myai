"""Fixed-path isolated pinned Parakeet worker. No network, shell or logging.

Invoked only by IsolatedPinnedParakeetSTT with python -I and a bounded,
strict config; stdout is a single schema-checked reply or nothing. Inference
loads pinned CPU model weights only after child-only resource limits apply.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.voice_parakeet_isolated import (
    MAX_PCM_BYTES, parakeet_worker_argv, validate_parakeet_config,
)


def main():
    try:
        if len(sys.argv) != 2 or len(sys.argv[1]) > 1400:
            return 2
        raw = json.loads(sys.argv[1])
        config = validate_parakeet_config(raw)
        # Reject values that could have passed a different parent schema.
        parakeet_worker_argv(config)
        from core.voice_stt_child_limits import apply_child_limits
        apply_child_limits()
        # No writable on-disk PCM, no remote request or arbitrary model plugin.
        data = sys.stdin.buffer.read(MAX_PCM_BYTES + 1)
        if not 0 < len(data) <= MAX_PCM_BYTES or len(data) % 2:
            return 2
        from modules.voice.sherpa_onnx_provider import SherpaOnnxParakeetSTT
        provider = SherpaOnnxParakeetSTT(
            model_name=config["model_name"],
            trusted_model_file_hashes=config["trusted_model_file_hashes"],
            num_threads=config["num_threads"],
            language=config["language"],
            sample_rate=config["sample_rate"],
            channels=config["channels"],
            sample_width=config["sample_width"],
            device="cpu", compute_type="int8",
        )
        result = provider.transcribe(data)
        text = result.get("text")
        if type(text) is not str or len(text) > 4096:
            return 2
        # Expected language from the configured Swedish-only pipeline;
        # this is NOT a measured Parakeet language-detection result.
        reply = json.dumps(
            {"text": text, "language": "sv", "confidence": None},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        if len(reply) > 8192:
            return 2
        sys.stdout.buffer.write(reply)
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        # Never leak speech audio, model names or native model errors.
        return 2


if __name__ == "__main__":
    sys.exit(main())
