"""Experimental, opt-in isolated FasterWhisper STT with HARD subprocess deadline.

The voice factory only enables this for its genuine built-in FasterWhisperSTT
with voice.stt_process_isolation_enabled=True (default False).

A fresh worker must load a cached model for each utterance, which can be
slow and memory-heavy; keep off on production until profiled. stdin carries
bounded PCM directly, stdout carries bounded JSON; neither audio, process
argv, transcript nor exceptions are logged. Child is offline-only.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from core.voice_stt_bounded_io import exchange_bounded, OversizedSTTOutput
from core.voice_stt_process_group import terminate_owned_group
from core.voice_stt_reply import decode_stt_reply
from core.voice_stt_child_limits import add_limit_environment, validated_limits

MAX_PCM_BYTES = 2 * 1024 * 1024
MAX_REPLY_BYTES = 8192
WORKER = Path(__file__).resolve().parent / "voice_stt_worker.py"
KNOWN_MODELS = frozenset({"tiny", "base", "small", "medium", "large-v3"})
KNOWN_COMPUTE = frozenset({"default", "int8", "int8_float16", "float16", "float32"})
KNOWN_DEVICES = frozenset({"auto", "cpu", "cuda"})
KNOWN_LANGUAGES = frozenset({"sv", "en"})
CLEAN_KEYS = frozenset({"text", "language", "confidence"})


def bounded_seconds(value):
    if type(value) not in (float, int):
        raise ValueError("Invalid isolated STT timeout")
    if not 1 <= value <= 300 or not math.isfinite(value):
        raise ValueError("Invalid isolated STT timeout")
    return float(value)


def worker_argv(config):
    """No executable or worker path supplied by user or LLM input."""
    if type(config) is not dict:
        raise ValueError("Invalid isolated STT configuration")
    if set(config) != {"model_name", "device", "compute_type", "language",
                       "sample_rate", "channels", "sample_width"}:
        raise ValueError("Invalid isolated STT configuration")
    fields = (
        ("model_name", KNOWN_MODELS), ("device", KNOWN_DEVICES),
        ("compute_type", KNOWN_COMPUTE), ("language", KNOWN_LANGUAGES),
    )
    for key, allowed in fields:
        if type(config[key]) is not str or config[key] not in allowed:
            raise ValueError("Unsupported isolated STT setting")
    if (type(config["sample_rate"]) is not int
            or config["sample_rate"] != 16000
            or type(config["channels"]) is not int or config["channels"] != 1
            or type(config["sample_width"]) is not int or config["sample_width"] != 2):
        raise ValueError("Unsupported isolated STT audio format")
    return [sys.executable, "-I", str(WORKER), json.dumps(config, separators=(",", ":"))]


def run_deadlined(argv, audio, seconds, *, popen=subprocess.Popen,
                 cpu_seconds=0, virtual_memory_mib=0):
    """Kill full owned process group on deadline, not merely Python thread.

    This only runs our trusted, fixed worker from worker_argv. Suppresses
    model stderr and never includes worker stdout/error in an exception.
    """
    timeout = bounded_seconds(seconds)
    if (type(audio) not in (bytes, bytearray)
            or not 0 < len(audio) <= MAX_PCM_BYTES):
        raise ValueError("Invalid or oversized isolated STT PCM")
    environment = add_limit_environment(
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
    try:
        proc = popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=True,
            cwd="/", env=environment,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        # Startup failure may contain a private executable path, tokens
        # or native error text. Never expose or chain that exception.
        # Popen did not return an owned process handle for cleanup.
        raise RuntimeError("Isolated STT worker start failed") from None
    deadline = time.monotonic() + timeout
    try:
        output = exchange_bounded(
            proc, bytes(audio), deadline=deadline,
            max_reply_bytes=MAX_REPLY_BYTES,
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Isolated STT process deadline exceeded")
        proc.wait(timeout=remaining)
    except (TimeoutError, subprocess.TimeoutExpired):
        # A helper may keep stdout open after its leader exits. Always
        # verify the FULL group is stopped before surfacing a timeout.
        terminate_owned_group(proc)
        raise TimeoutError("Isolated STT process deadline exceeded") from None
    except OversizedSTTOutput:
        # Surface only a fixed category; the child's actual output is
        # never echoed or stored and the group must first be reaped.
        terminate_owned_group(proc)
        raise RuntimeError("Invalid isolated STT output") from None
    except BaseException:
        # Even a broken pipe may leave a native child alive.
        # Refuse the reply unless its group is fully cleaned up.
        terminate_owned_group(proc)
        raise RuntimeError("Isolated STT worker failed") from None

    # Successful pipe EOF/leader exit are not sufficient: native helper
    # descendants could still retain RAM inside the same group.
    terminate_owned_group(proc)
    if proc.returncode != 0:
        raise RuntimeError("Isolated STT worker failed")
    try:
        return decode_stt_reply(output)
    except ValueError:
        # Always expose only a fixed category, never invalid JSON,
        # duplicate field values or private child output.
        raise RuntimeError("Invalid isolated STT JSON or schema") from None


class IsolatedFasterWhisperSTT:
    """Same voice-provider API. No shared loaded model across utterances."""

    def __init__(self, *, timeout_seconds=45, cpu_seconds=0,
                 virtual_memory_mib=0, **config):
        self.timeout_seconds = bounded_seconds(timeout_seconds)
        self.cpu_seconds, self.virtual_memory_mib = validated_limits(
            cpu_seconds, virtual_memory_mib
        )
        self._config = dict(config)
        self._argv = worker_argv(self._config)

    def transcribe(self, audio):
        return run_deadlined(
            self._argv, audio, self.timeout_seconds,
            cpu_seconds=self.cpu_seconds,
            virtual_memory_mib=self.virtual_memory_mib,
        )

    def release_for_inference(self):
        # The worker exits after each utterance; no persistent model.
        return False
