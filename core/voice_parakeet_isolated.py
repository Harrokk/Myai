"""Fixed, offline, one-shot Parakeet worker contract.

The isolated worker is shipped as core/voice_parakeet_worker.py and is invoked
with python -I. No shell, arbitrary executable, network, microphone, or
model operation occurs when importing or constructing this adapter.
"""
import json
import os
from pathlib import Path
import re
import sys
import threading

from core.voice_model_provenance import verify_stt_model_files
from core.voice_stt_child_limits import validated_limits
from core.voice_stt_process import bounded_seconds, run_deadlined
from modules.voice.sherpa_onnx_provider import SherpaOnnxParakeetSTT


_WORKER = Path(__file__).resolve().parent / "voice_parakeet_worker.py"
_SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_PCM_BYTES = 30 * 16000 * 2
_EXPECTED = set(SherpaOnnxParakeetSTT.MODEL_FILES)
_CONFIG_KEYS = {"model_name", "trusted_model_file_hashes",
                "num_threads", "language", "sample_rate",
                "channels", "sample_width"}


def validate_parakeet_config(config):
    """Validate input independently in parent and child."""
    if type(config) is not dict or set(config) != _CONFIG_KEYS:
        raise ValueError("Invalid isolated Parakeet config")
    root = config["model_name"]
    if (type(root) is not str or not root.startswith("/")
            or not 0 < len(root) <= 512 or "\x00" in root):
        raise ValueError("Invalid isolated Parakeet model directory")
    manifest = config["trusted_model_file_hashes"]
    if (type(manifest) is not dict or set(manifest) != _EXPECTED
            or any(
                type(name) is not str or type(digest) is not str
                or not _SHA.fullmatch(digest)
                for name, digest in manifest.items()
            )):
        raise ValueError("Invalid isolated Parakeet manifest")
    if (config["language"] != "sv"
            or type(config["num_threads"]) is not int
            or not 1 <= config["num_threads"] <= 4
            or type(config["sample_rate"]) is not int
            or config["sample_rate"] != 16000
            or type(config["channels"]) is not int
            or config["channels"] != 1
            or type(config["sample_width"]) is not int
            or config["sample_width"] != 2):
        raise ValueError("Invalid isolated Parakeet audio config")
    return dict(config, trusted_model_file_hashes=dict(manifest))


def parakeet_worker_argv(config):
    clean = validate_parakeet_config(config)
    data = json.dumps(clean, separators=(",", ":"), sort_keys=True)
    if len(data) > 1400:
        raise ValueError("Oversized isolated Parakeet config")
    return [sys.executable, "-I", str(_WORKER), data]


class IsolatedPinnedParakeetSTT:
    """Opt-in CPU-only one-shot STT with real hard timeout and Stop signal.

    The supplied SHA256 manifest MUST come from a separately reviewed pinned
    release. No live factory currently constructs this in production.
    """

    def __init__(self, *, model_name, trusted_model_file_hashes,
                 timeout_seconds=45, cpu_seconds=0, virtual_memory_mib=0,
                 num_threads=2, language="sv", sample_rate=16000,
                 channels=1, sample_width=2):
        config = validate_parakeet_config({
            "model_name": model_name,
            "trusted_model_file_hashes": trusted_model_file_hashes,
            "num_threads": num_threads,
            "language": language,
            "sample_rate": sample_rate,
            "channels": channels,
            "sample_width": sample_width,
        })
        self.model_name = config["model_name"]
        self._config = config
        self._argv = parakeet_worker_argv(config)
        self.timeout_seconds = bounded_seconds(timeout_seconds)
        self.cpu_seconds, self.virtual_memory_mib = validated_limits(
            cpu_seconds, virtual_memory_mib
        )
        self._cancel = threading.Event()
        self._active = threading.Lock()

    def prepare_verified_model(self):
        # Hash local file bytes before minting any trusted vote identity.
        return verify_stt_model_files(
            self.model_name, family="parakeet",
            expected_sha256=self._config["trusted_model_file_hashes"],
        )

    def transcribe(self, audio):
        if (type(audio) is not bytes or not 0 < len(audio) <= MAX_PCM_BYTES
                or len(audio) % 2):
            raise ValueError("Invalid isolated Parakeet PCM")
        if self._cancel.is_set():
            raise RuntimeError("Isolated Parakeet session stopped")
        if not self._active.acquire(blocking=False):
            raise RuntimeError("Isolated Parakeet already running")
        try:
            # Both parent and child independently check the same pinned files.
            bundle = self.prepare_verified_model()
            if self._cancel.is_set():
                raise RuntimeError("Isolated Parakeet session stopped")
            output = run_deadlined(
                self._argv, audio, self.timeout_seconds,
                cpu_seconds=self.cpu_seconds,
                virtual_memory_mib=self.virtual_memory_mib,
                cancel_event=self._cancel,
            )
            if self._cancel.is_set() or not bundle.is_current():
                raise RuntimeError("Isolated Parakeet result invalidated")
            return output
        finally:
            self._active.release()

    def request_cancel(self):
        """Fast, nonblocking Stop; the shared bounded IPC kills the group."""
        self._cancel.set()
        return True

    def resume(self):
        """A new explicit session may rearm only after full worker cleanup."""
        if not self._active.acquire(blocking=False):
            raise RuntimeError("Isolated Parakeet worker cleanup incomplete")
        try:
            self._cancel.clear()
        finally:
            self._active.release()

    def release_for_inference(self):
        # A one-shot child never persists after transcribe() returns.
        # Do not allow GenieX handoff while native cleanup is outstanding.
        if not self._active.acquire(blocking=False):
            self.request_cancel()
            raise RuntimeError("Isolated Parakeet worker cleanup incomplete")
        self._active.release()
        return False

    def close(self):
        self.request_cancel()
        return self.release_for_inference()
