"""Cached FasterWhisper worker serving up to 8 bounded PCM frames.

Launched only by voice_stt_persistent.py using python -I and allowlisted
model settings. Importing this module never loads the model. No logging,
network/model downloads or raw audio/transcripts appear in stderr.
"""
from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.voice_stt_process import MAX_PCM_BYTES, worker_argv
from core.voice_stt_persistent import (
    MAX_RESPONSE, MAX_UTTERANCES_PER_CHILD, REQUEST_NONCE_BYTES,
)


def read_exact(stream, length, *, allow_clean_eof=False):
    """Only an empty stream at a frame boundary is normal shutdown.

    Partial headers, nonces and audio are all protocol failures.
    """
    data = bytearray()
    while len(data) < length:
        piece = stream.read(length - len(data))
        if not piece:
            if allow_clean_eof and not data:
                return None
            raise EOFError()
        data.extend(piece)
    return bytes(data)


def main():
    try:
        if len(sys.argv) != 2 or len(sys.argv[1]) > 1024:
            return 2
        config = json.loads(sys.argv[1])
        worker_argv(config)
        from core.voice_stt_child_limits import apply_child_limits
        # Applies only inside this isolated child BEFORE model/native
        # dependencies load; leaves the parent/GenieX entirely untouched.
        apply_child_limits()
        from modules.voice.providers import FasterWhisperSTT
        provider = FasterWhisperSTT(**config)
        # Parent enforces a lower configurable cap, but the child must
        # also have its own hard maximum, independent of parent health.
        for _ in range(MAX_UTTERANCES_PER_CHILD):
            try:
                header = read_exact(
                    sys.stdin.buffer, 4, allow_clean_eof=True,
                )
            except EOFError:
                return 2
            if header is None:
                return 0
            length = struct.unpack(">I", header)[0]
            if length < 1 or length > MAX_PCM_BYTES:
                return 2
            nonce = read_exact(sys.stdin.buffer, REQUEST_NONCE_BYTES)
            audio = read_exact(sys.stdin.buffer, length)
            answer = provider.transcribe(audio)
            text = answer.get("text")
            language = answer.get("language")
            if (type(text) is not str or len(text) > 4096
                    or type(language) is not str
                    or language not in {"sv", "en"}):
                return 2
            encoded = json.dumps({
                "text": text, "language": language, "confidence": None,
            }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(encoded) > MAX_RESPONSE:
                return 2
            sys.stdout.buffer.write(struct.pack(">I", REQUEST_NONCE_BYTES + len(encoded)))
            sys.stdout.buffer.write(nonce)
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()
        return 0
    except BaseException:
        # The parent treats truncated/absent reply as failure and kills
        # this process. Never leak model exceptions to stdout or stderr.
        return 2


if __name__ == "__main__":
    sys.exit(main())
