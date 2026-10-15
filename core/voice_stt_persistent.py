"""Experimental opt-in persistent FasterWhisper worker with hard IPC deadlines.

Unlike the one-shot subprocess in voice_stt_process, this keeps a model
cached across a strictly limited number of utterances in one *isolated*
OS process. The worker is never started by import or by the default
voice profile. No microphones, models or hardware are accessed in CI.

The parent never uses Python threads for timeouts. Nonblocking POSIX
pipes and one monotonic deadline cover BOTH audio upload and response
read, so a hung worker can be killed and reaped as an owned process
group. Unexpected exit, malformed replies and oversized frames are
fatal and cannot authorize a voice command. This is a Linux-only
experimental component; the regular one-shot mode remains the default
when isolation is explicitly enabled.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import sys
import threading
import time

from core.voice_stt_process import (
    MAX_PCM_BYTES, MAX_REPLY_BYTES, CLEAN_KEYS,
    KNOWN_LANGUAGES, bounded_seconds, worker_argv,
)

WORKER = Path(__file__).resolve().parent / "voice_stt_persistent_worker.py"
MAX_UTTERANCES_PER_CHILD = 8
FRAME_HEADER = 4
MAX_REQUEST = MAX_PCM_BYTES
MAX_RESPONSE = MAX_REPLY_BYTES


def bounded_utterances(value):
    if type(value) is not int or not 1 <= value <= MAX_UTTERANCES_PER_CHILD:
        raise ValueError("Invalid persistent STT worker request cap")
    return value


def parse_reply(raw):
    if type(raw) is not bytes or len(raw) > MAX_RESPONSE:
        raise RuntimeError("Invalid persistent STT response")
    try:
        decoded = json.loads(
            raw,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ValueError("Non-finite JSON value")
            ),
        )
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise RuntimeError("Invalid persistent STT response") from None
    if (
        type(decoded) is not dict
        or set(decoded) != CLEAN_KEYS
        or type(decoded["text"]) is not str
        or len(decoded["text"]) > 4096
        or type(decoded["language"]) is not str
        or decoded["language"] not in KNOWN_LANGUAGES
        or decoded["confidence"] is not None
    ):
        raise RuntimeError("Invalid persistent STT response")
    return decoded


def persistent_argv(config):
    # Same strict constructor-level model restrictions as one-shot.
    one_shot = worker_argv(config)
    return [one_shot[0], "-I", str(WORKER), one_shot[3]]


def offline_environment():
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": os.path.expanduser("~"),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "2",
    }


def _ready(fd, write, deadline, clock):
    remaining = deadline - clock()
    if remaining <= 0:
        raise TimeoutError("Persistent STT deadline exceeded")
    readable, writable, _ = select.select(
        [] if write else [fd], [fd] if write else [], [], remaining,
    )
    if not (writable if write else readable):
        raise TimeoutError("Persistent STT deadline exceeded")


def _send_all(fd, data, deadline, clock):
    pos = 0
    while pos < len(data):
        _ready(fd, True, deadline, clock)
        try:
            written = os.write(fd, data[pos:pos + 65536])
        except BlockingIOError:
            continue
        if written <= 0:
            raise RuntimeError("Persistent STT write failure")
        pos += written


def _recv_exact(fd, length, deadline, clock):
    data = bytearray()
    while len(data) < length:
        _ready(fd, False, deadline, clock)
        try:
            piece = os.read(fd, min(length - len(data), 65536))
        except BlockingIOError:
            continue
        if not piece:
            raise RuntimeError("Persistent STT worker closed the pipe")
        data.extend(piece)
    return bytes(data)


def exchange(proc, audio, timeout, *, clock=time.monotonic):
    """One request/response. Caller owns exclusive worker access."""
    bounded_seconds(timeout)
    if type(audio) not in (bytes, bytearray) or not 0 < len(audio) <= MAX_REQUEST:
        raise ValueError("Invalid persistent STT PCM")
    if proc.poll() is not None:
        raise RuntimeError("Persistent STT worker is not running")
    deadline = clock() + timeout
    _send_all(
        proc.stdin.fileno(), struct.pack(">I", len(audio)) + bytes(audio),
        deadline, clock,
    )
    header = _recv_exact(proc.stdout.fileno(), FRAME_HEADER, deadline, clock)
    size = struct.unpack(">I", header)[0]
    if size < 1 or size > MAX_RESPONSE:
        raise RuntimeError("Oversized persistent STT response")
    result = parse_reply(_recv_exact(
        proc.stdout.fileno(), size, deadline, clock,
    ))
    return result


def terminate_owned(proc):
    """Try to terminate the owned process group, reap, no false success."""
    if proc is None:
        return
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Persistent STT process cleanup incomplete") from None
    finally:
        for name in ("stdin", "stdout"):
            stream = getattr(proc, name, None)
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass


class PersistentFasterWhisperSTT:
    """Cached model with bounded lifetime, fail-closed after any IPC fault."""

    def __init__(self, *, timeout_seconds=45, max_utterances=4, **config):
        self.timeout_seconds = bounded_seconds(timeout_seconds)
        self.max_utterances = bounded_utterances(max_utterances)
        self._argv = persistent_argv(dict(config))
        self._worker = None
        self._count = 0
        self._lock = threading.Lock()

    def _spawn(self):
        self._worker = subprocess.Popen(
            self._argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd="/", env=offline_environment(),
            bufsize=0, start_new_session=True,
        )
        self._count = 0

    def _release(self):
        proc = self._worker
        self._worker = None
        self._count = 0
        terminate_owned(proc)

    def transcribe(self, audio):
        with self._lock:
            # Reject malformed audio BEFORE spawning or touching a model.
            if (type(audio) not in (bytes, bytearray)
                    or not 0 < len(audio) <= MAX_REQUEST):
                raise ValueError("Invalid persistent STT PCM")
            if self._worker is None:
                self._spawn()
            try:
                result = exchange(self._worker, audio, self.timeout_seconds)
                self._count += 1
                # A fresh worker after N uses avoids unbounded cached
                # model/resource accumulation between long conversations.
                if self._count >= self.max_utterances:
                    self._release()
                return result
            except BaseException:
                # Includes timeout, failed IPC, and interrupted caller.
                # A broken worker MUST NOT be reused on next request.
                self._release()
                raise

    def release_for_inference(self):
        """Free model/RAM before switching to a heavier local LLM."""
        with self._lock:
            was_running = self._worker is not None
            if was_running:
                self._release()
            return was_running

    def close(self):
        return self.release_for_inference()
