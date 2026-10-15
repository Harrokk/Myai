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

import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import threading
import time

from core.voice_stt_process_group import terminate_owned_group
from core.voice_stt_reply import decode_stt_reply
from core.voice_stt_child_limits import add_limit_environment, validated_limits
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
    """Decode the same strict IPC reply schema as one-shot STT."""
    try:
        return decode_stt_reply(raw)
    except ValueError:
        raise RuntimeError("Invalid persistent STT response") from None


def persistent_argv(config):
    # Same strict constructor-level model restrictions as one-shot.
    one_shot = worker_argv(config)
    return [one_shot[0], "-I", str(WORKER), one_shot[3]]


def offline_environment(*, cpu_seconds=0, virtual_memory_mib=0):
    return add_limit_environment(
        {
            "PATH": "/usr/bin:/bin",
            "HOME": os.path.expanduser("~"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "OMP_NUM_THREADS": "2",
        },
        cpu_seconds=cpu_seconds,
        virtual_memory_mib=virtual_memory_mib,
    )


def _ready(fd, write, deadline, clock, cancel_event=None):
    # select() is a deadline guard, not a cancellation primitive.
    # Bound each wait to 100 ms so an explicit stop can interrupt a
    # sleeping native STT child without waiting for 45–300 seconds.
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Persistent STT request cancelled")
    remaining = deadline - clock()
    if remaining <= 0:
        raise TimeoutError("Persistent STT deadline exceeded")
    readable, writable, _ = select.select(
        [] if write else [fd], [fd] if write else [], [],
        min(remaining, 0.1) if cancel_event is not None else remaining,
    )
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Persistent STT request cancelled")
    if not (writable if write else readable):
        if cancel_event is not None and clock() < deadline:
            return False
        raise TimeoutError("Persistent STT deadline exceeded")
    return True


def _send_all(fd, data, deadline, clock, cancel_event=None,
              reply_fd=None):
    """Write all PCM or reject a worker replying/closing stdout early.

    Native worker protocol requires FULL PCM before any response. A
    half-closed child can otherwise leave the writer waiting until the
    entire 45-300s deadline, even though it has already answered.
    """
    pos = 0
    while pos < len(data):
        if reply_fd is None:
            if not _ready(fd, True, deadline, clock, cancel_event):
                continue
        else:
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Persistent STT request cancelled")
            remaining = deadline - clock()
            if remaining <= 0:
                raise TimeoutError("Persistent STT deadline exceeded")
            read_ready, write_ready, _ = select.select(
                [reply_fd], [fd], [],
                min(remaining, 0.1) if cancel_event is not None else remaining,
            )
            if cancel_event is not None and cancel_event.is_set():
                raise RuntimeError("Persistent STT request cancelled")
            if read_ready:
                # Readable also covers EOF, even with zero reply bytes.
                # Never accept a forged transcript before full PCM.
                raise RuntimeError("Persistent STT reply before PCM complete")
            if not write_ready:
                continue
        try:
            written = os.write(fd, data[pos:pos + 65536])
        except BlockingIOError:
            continue
        if written <= 0:
            raise RuntimeError("Persistent STT write failure")
        pos += written


def _recv_exact(fd, length, deadline, clock, cancel_event=None):
    data = bytearray()
    while len(data) < length:
        if not _ready(fd, False, deadline, clock, cancel_event):
            continue
        try:
            piece = os.read(fd, min(length - len(data), 65536))
        except BlockingIOError:
            continue
        if not piece:
            raise RuntimeError("Persistent STT worker closed the pipe")
        data.extend(piece)
    return bytes(data)


def exchange(proc, audio, timeout, *, clock=time.monotonic, cancel_event=None):
    """One request/response. Caller owns exclusive worker access."""
    bounded_seconds(timeout)
    if type(audio) not in (bytes, bytearray) or not 0 < len(audio) <= MAX_REQUEST:
        raise ValueError("Invalid persistent STT PCM")
    if proc.poll() is not None:
        raise RuntimeError("Persistent STT worker is not running")
    deadline = clock() + timeout
    _send_all(
        proc.stdin.fileno(), struct.pack(">I", len(audio)) + bytes(audio),
        deadline, clock, cancel_event,
        reply_fd=proc.stdout.fileno(),
    )
    header = _recv_exact(
        proc.stdout.fileno(), FRAME_HEADER, deadline, clock, cancel_event,
    )
    size = struct.unpack(">I", header)[0]
    if size < 1 or size > MAX_RESPONSE:
        raise RuntimeError("Oversized persistent STT response")
    result = parse_reply(_recv_exact(
        proc.stdout.fileno(), size, deadline, clock, cancel_event,
    ))
    if cancel_event is not None and cancel_event.is_set():
        # A reply racing with a user's Stop must not authorize an
        # assistant/tool invocation after the stop request.
        raise RuntimeError("Persistent STT request cancelled")
    return result


def terminate_owned(proc):
    """Also kill group descendants after the STT leader has exited."""
    return terminate_owned_group(proc)



class PersistentFasterWhisperSTT:
    """Cached model with bounded lifetime, fail-closed after any IPC fault."""

    def __init__(self, *, timeout_seconds=45, max_utterances=4,
                 cpu_seconds=0, virtual_memory_mib=0, **config):
        self.timeout_seconds = bounded_seconds(timeout_seconds)
        self.max_utterances = bounded_utterances(max_utterances)
        self.cpu_seconds, self.virtual_memory_mib = validated_limits(
            cpu_seconds, virtual_memory_mib
        )
        self._argv = persistent_argv(dict(config))
        self._worker = None
        self._count = 0
        self._cleanup_required = False
        self._lock = threading.Lock()
        self._cancel = threading.Event()

    def _spawn(self):
        try:
            self._worker = subprocess.Popen(
                self._argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, cwd="/",
                env=offline_environment(
                    cpu_seconds=self.cpu_seconds,
                    virtual_memory_mib=self.virtual_memory_mib,
                ),
                bufsize=0, start_new_session=True,
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            # No process handle returned; never expose private native
            # error text or claim a successfully started worker.
            raise RuntimeError("Persistent STT worker start failed") from None
        self._count = 0
        try:
            # select() only prevents blocking if the actual pipe fd is
            # O_NONBLOCK. Large pipe writes must obey the STT deadline.
            os.set_blocking(self._worker.stdin.fileno(), False)
            os.set_blocking(self._worker.stdout.fileno(), False)
        except BaseException:
            # A partially initialized worker can still own native RAM.
            # Retain the handle if reaping fails, so no duplicate model
            # is launched and no private pipe exception is exposed.
            self._release()
            raise RuntimeError("Persistent STT IPC setup failed") from None

    def _release(self):
        proc = self._worker
        if proc is None:
            self._count = 0
            self._cleanup_required = False
            return
        try:
            terminate_owned(proc)
        except Exception:
            # A failed reap must NEVER discard the last process handle,
            # or let a new worker load a second native model next time.
            # Retain it for an explicit close()/retry. Hide OS details.
            self._cleanup_required = True
            raise RuntimeError(
                "Persistent STT process cleanup incomplete"
            ) from None
        self._worker = None
        self._count = 0
        self._cleanup_required = False

    def transcribe(self, audio):
        with self._lock:
            if self._cancel.is_set():
                raise RuntimeError("Persistent STT request cancelled")
            # Reject malformed audio BEFORE spawning or touching a model.
            if (type(audio) not in (bytes, bytearray)
                    or not 0 < len(audio) <= MAX_REQUEST):
                raise ValueError("Invalid persistent STT PCM")
            if self._cleanup_required:
                # The previous child could not be confirmed reaped. A
                # new process would double-load the model and may make
                # memory pressure much worse on the 16 GB board.
                raise RuntimeError("Persistent STT cleanup pending")
            if self._worker is None:
                self._spawn()
            try:
                result = exchange(
                    self._worker, audio, self.timeout_seconds,
                    cancel_event=self._cancel,
                )
            except (OSError, ValueError):
                # OS pipe/select failures may contain private paths,
                # descriptors or native messages. They must never escape
                # into the voice status, even if teardown itself succeeds.
                # No partial transcript is trusted after a transport fault.
                self._release()
                raise RuntimeError("Persistent STT IPC transfer failed") from None
            except BaseException:
                # No partial/late transcript is authorized after any
                # transport error. Try cleanup exactly once per failure.
                self._release()
                raise

            if self._cancel.is_set():
                self._release()
                raise RuntimeError("Persistent STT request cancelled")
            self._count += 1
            # Cleanup errors AFTER a successful reply still block its
            # use by the caller and retain the process for retry; do
            # not mask or retry cleanup a second time in this handler.
            if self._count >= self.max_utterances:
                self._release()
            return result

    def request_cancel(self):
        """Nonblocking stop signal safe to issue from the control thread."""
        self._cancel.set()

    def resume(self):
        """Explicitly re-arm only after a newly started voice session."""
        with self._lock:
            if self._cleanup_required:
                raise RuntimeError("Persistent STT cleanup pending")
            self._cancel.clear()

    def release_for_inference(self):
        """Free model/RAM before switching to a heavier local LLM."""
        with self._lock:
            was_running = self._worker is not None
            if was_running:
                self._release()
            return was_running

    def close(self):
        self.request_cancel()
        return self.release_for_inference()
