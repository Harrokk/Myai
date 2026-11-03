"""Source-only opt-in Canary/Whisper native STT adapters.

A separately trusted factory must supply exact model/binary SHA256 hashes
from an independently audited release. No production factory registers this
provider; it cannot be enabled through the tiered voice config.

The parent uses a sealed memory-only WAV and a *fixed checked-in* python -I
worker. Child validates native bytes and launches a fixed CPU CLI by execve.
Every exit, timeout and Stop must clean up the owned process group.
No shell, tempfile, leaked stderr or arbitrary CLI arguments.
"""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
import time

from core.voice_candidate_audio_memfd import (
    MAX_PCM_BYTES, sealed_pcm16_wav_memfd,
)
from core.voice_candidate_cli_contract import parse_candidate_stdout
from core.voice_candidate_preflight import (
    VerifiedCandidateProfile, verify_candidate_profile,
)
from core.voice_stt_child_limits import add_limit_environment, validated_limits
from core.voice_stt_process import bounded_seconds
from core.voice_stt_process_group import terminate_owned_group


_WORKER = Path(__file__).resolve().parent / "voice_candidate_worker.py"
_MAX_OUTPUT = 32768


def _launch_native_candidate_worker(argv, **kwargs):
    """Overridden only in hosted unit tests, never by user/LLM input."""
    return subprocess.Popen(argv, **kwargs)


def _read_bounded_native_output(proc, deadline, stopped):
    if getattr(proc, "stdout", None) is None:
        raise RuntimeError("Invalid candidate stdout")
    fd = proc.stdout.fileno()
    os.set_blocking(fd, False)
    output = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        while selector.get_map():
            if stopped():
                raise RuntimeError("Native candidate cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Native candidate deadline exceeded")
            events = selector.select(min(remaining, 0.1))
            for key, _ in events:
                take = min(8192, _MAX_OUTPUT + 1 - len(output))
                if take <= 0:
                    raise RuntimeError("Native candidate stdout exceeded limit")
                data = os.read(key.fd, take)
                if data:
                    output.extend(data)
                    if len(output) > _MAX_OUTPUT:
                        raise RuntimeError("Native candidate stdout exceeded limit")
                else:
                    selector.unregister(fd)
    return bytes(output)


def _safe_native_env(cpu_seconds, virtual_memory_mib):
    return add_limit_environment(
        {
            "PATH": "/usr/bin:/bin",
            "HOME": "/",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "GGML_VULKAN_DEVICE": "-1",
            "OMP_NUM_THREADS": "2",
        },
        cpu_seconds=cpu_seconds,
        virtual_memory_mib=virtual_memory_mib,
    )


class IsolatedPinnedNativeCandidateSTT:
    """Disabled-by-default local STT with strict profile/manifest preflight."""

    def __init__(self, *, profile, model_sha256, runtime_sha256,
                 timeout_seconds=45, cpu_seconds=0,
                 virtual_memory_mib=0, threads=2):
        if type(profile) is not VerifiedCandidateProfile or not profile.is_current():
            raise ValueError("Untrusted native candidate identity")
        if type(threads) is not int or not 1 <= threads <= 4:
            raise ValueError("Invalid native candidate threads")
        # Re-verify exact source-supplied hashes; a profile cannot be
        # silently re-used with unrelated digests or binaries.
        attest = verify_candidate_profile(
            profile.profile,
            model_root=profile.model_root,
            model_sha256=model_sha256,
            runtime_root=profile.runtime_root,
            runtime_sha256=runtime_sha256,
        )
        if (not attest.is_current()
                or attest.model_revision != profile.model_revision
                or attest.runtime_revision != profile.runtime_revision):
            raise ValueError("Native candidate verification mismatch")
        self.model_name = attest.model_root
        self._profile = attest
        self._model_sha256 = model_sha256
        self._runtime_sha256 = runtime_sha256
        self._threads = threads
        self.timeout_seconds = bounded_seconds(timeout_seconds)
        self.cpu_seconds, self.virtual_memory_mib = validated_limits(
            cpu_seconds, virtual_memory_mib,
        )
        self._cancel = threading.Event()
        self._active = threading.Lock()

    def prepare_verified_model(self):
        if not self._profile.is_current():
            raise RuntimeError("Native candidate model changed")
        return self._profile._model_bundle

    def transcribe(self, audio):
        if (type(audio) is not bytes or not 0 < len(audio) <= MAX_PCM_BYTES
                or len(audio) % 2):
            raise ValueError("Invalid native candidate PCM")
        if self._cancel.is_set():
            raise RuntimeError("Native candidate stopped")
        if not self._active.acquire(blocking=False):
            raise RuntimeError("Native candidate is already running")
        proc = None
        raw = None
        native_returncode = None
        try:
            deadline = time.monotonic() + self.timeout_seconds
            if not self._profile.is_current() or self._cancel.is_set():
                raise RuntimeError("Native candidate identity changed or stopped")
            config = {
                "profile": self._profile.profile,
                "model_root": self._profile.model_root,
                "model_sha256": self._model_sha256,
                "runtime_root": self._profile.runtime_root,
                "runtime_sha256": self._runtime_sha256,
                "threads": self._threads,
            }
            raw_config = json.dumps(config, sort_keys=True, separators=(",", ":"))
            if len(raw_config) > 2048:
                raise ValueError("Oversized native candidate configuration")
            with sealed_pcm16_wav_memfd(audio) as (fd, _):
                if self._cancel.is_set() or time.monotonic() >= deadline:
                    raise RuntimeError("Native candidate stopped or expired")
                try:
                    proc = _launch_native_candidate_worker(
                        [sys.executable, "-I", str(_WORKER),
                         raw_config, str(fd)],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                        pass_fds=(fd,),
                        cwd="/",
                        env=_safe_native_env(
                            self.cpu_seconds, self.virtual_memory_mib,
                        ),
                    )
                except (OSError, ValueError, subprocess.SubprocessError):
                    raise RuntimeError("Native candidate startup failed") from None
                try:
                    raw = _read_bounded_native_output(
                        proc, deadline, self._cancel.is_set,
                    )
                    while True:
                        if self._cancel.is_set():
                            raise RuntimeError("Native candidate stopped")
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("Native candidate deadline exceeded")
                        try:
                            proc.wait(timeout=min(0.1, remaining))
                            native_returncode = proc.returncode
                            break
                        except subprocess.TimeoutExpired:
                            continue
                finally:
                    # This also reaps workers that returned a plausible
                    # transcript before their helper descendants exited.
                    terminate_owned_group(proc)
                    proc = None
            if self._cancel.is_set() or not self._profile.is_current():
                raise RuntimeError("Native candidate reply revoked")
            # Exact child exit=0 and owned group cleanup are prerequisites.
            if native_returncode != 0 or raw is None:
                # Public numeric POSIX status only, but limit to audited
                # constant categories. No stderr, PCM, transcript or paths.
                status_names = {
                    1: "exit_1", 2: "exit_2", 3: "exit_3",
                    4: "exit_4", 10: "exit_10", 11: "exit_11",
                    -6: "signal_abort", -9: "signal_kill",
                    -11: "signal_segv",
                }
                reason = status_names.get(native_returncode, "other")
                raise RuntimeError("Native candidate failed (" + reason + ")")
            try:
                return parse_candidate_stdout(self._profile.profile, raw)
            except ValueError as exc:
                # Constant, allowlisted parser categories only. Never reveal
                # the native stdout, transcript bytes, model paths or audio.
                safe_parse_codes = {
                    "Unverified native Canary response": "canary_status",
                    "No native Canary transcription": "canary_empty",
                    "Incomplete native Canary transcript": "canary_incomplete",
                    "Native Canary language disagreement": "canary_language",
                    "Invalid native Whisper JSON": "whisper_json",
                    "Unverified native Whisper language or structure": "whisper_schema",
                    "Unverified native Whisper segment": "whisper_segment",
                    "Duplicate native Whisper JSON key": "whisper_duplicate",
                    "Unsafe native STT transcript": "unsafe_transcript",
                    "Unsafe native STT output": "unsafe_stdout",
                    "Invalid native STT UTF-8": "utf8",
                    "Invalid native STT result": "invalid_result",
                }
                code = safe_parse_codes.get(str(exc), "other")
                raise RuntimeError("Native candidate output invalid (" +
                                   code + ")") from None
        except TimeoutError:
            raise TimeoutError("Native candidate deadline exceeded") from None
        except (ValueError, RuntimeError):
            raise
        except Exception:
            raise RuntimeError("Native candidate failed") from None
        finally:
            if proc is not None:
                terminate_owned_group(proc)
            self._active.release()

    def request_cancel(self):
        self._cancel.set()
        return True

    def resume(self):
        if not self._active.acquire(blocking=False):
            raise RuntimeError("Native candidate cleanup incomplete")
        try:
            self._cancel.clear()
        finally:
            self._active.release()

    def release_for_inference(self):
        if not self._active.acquire(blocking=False):
            self.request_cancel()
            raise RuntimeError("Native candidate cleanup incomplete")
        self._active.release()
        return False

    def close(self):
        self.request_cancel()
        return self.release_for_inference()
