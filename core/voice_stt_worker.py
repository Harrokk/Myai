"""Trusted on-disk worker for isolated PCM->FasterWhisper transcript.

Started with python -I by core.voice_stt_process. No shell, network
requests or Python plugin imports. All output is a single bounded JSON
result; provider exceptions and raw audio are deliberately suppressed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

# Python -I intentionally excludes cwd/PYTHONPATH; add only our own
# fixed checked-out repository root, never a user-input module path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.voice_stt_process import MAX_PCM_BYTES, worker_argv


def main():
    try:
        if len(sys.argv) != 2 or len(sys.argv[1]) > 1024:
            return 2
        config = json.loads(sys.argv[1])
        # Reuse exactly the same schema check as the parent.
        worker_argv(config)
        from core.voice_stt_child_limits import apply_child_limits
        # Applies only inside this isolated child BEFORE model/native
        # dependencies load; leaves the parent/GenieX entirely untouched.
        apply_child_limits()
        data = sys.stdin.buffer.read(MAX_PCM_BYTES + 1)
        if not 0 < len(data) <= MAX_PCM_BYTES:
            return 2
        from modules.voice.providers import FasterWhisperSTT
        # Isolated workers must not persist private microphone PCM to a
        # NamedTemporaryFile: SIGKILL/board power loss cannot run unlink.
        # The local built-in provider consumes a bounded numpy PCM array.
        provider = FasterWhisperSTT(**config, pcm_memory_only=True)
        answer = provider.transcribe(data)
        text = answer.get("text")
        language = answer.get("language")
        if (type(text) is not str or len(text) > 4096
                or type(language) is not str or language not in {"sv", "en"}):
            return 2
        result = json.dumps(
            {"text": text, "language": language, "confidence": None},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        if len(result) > 8192:
            return 2
        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        # Never print STT libraries' errors or private path/audio to logs.
        return 2


if __name__ == "__main__":
    sys.exit(main())
