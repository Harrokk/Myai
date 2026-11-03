"""Source-only Canary/Whisper ARM64 provenance gates for the MyAI voice pilot.

This module DOES NOT perform transcription, install models, invoke binaries,
load shared libraries, or grant STT votes. It verifies the operator-pinned
local model bytes and a separate ARM64 ELF executable before future runtime
integration. Production factory wiring remains explicitly unavailable.

A pinned digest must come from a reviewed release manifest OUTSIDE the
downloaded model/binary tree. No hard-coded fictitious public SHA values.
"""
from pathlib import Path
import re
import stat

from core.voice_model_provenance import verify_stt_model_files


_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
# Exact model versions and runtimes with independently reviewed language support.
_PROFILES = {
    "canary-1b-v2-q8": (
        "canary", "transcribe_cpp", "canary-1b-v2-Q8_0.gguf", "transcribe-cli",
    ),
    "whisper-large-v3-turbo": (
        "whisper", "whisper_cpp", "ggml-large-v3-turbo.bin", "whisper-cli",
    ),
}
_ARM64_MACHINE = 183
_MAX_RUNTIME_BYTES = 256 * 1024 * 1024
_ISSUER = object()


class VerifiedCandidateProfile:
    """Immutable pair of checked model bytes and checked ARM64 runtime bytes."""
    __slots__ = (
        "profile", "family", "engine", "model_root", "model_file",
        "runtime_root", "runtime_file", "_model_bundle", "_runtime_bundle",
        "_issuer",
    )

    def __init__(self, token, *, profile, family, engine, model_file,
                 runtime_file, model_bundle, runtime_bundle):
        if token is not _ISSUER:
            raise ValueError("Untrusted voice candidate profile")
        values = {
            "profile": profile, "family": family, "engine": engine,
            "model_root": model_bundle.root, "model_file": model_file,
            "runtime_root": runtime_bundle.root, "runtime_file": runtime_file,
            "_model_bundle": model_bundle, "_runtime_bundle": runtime_bundle,
            "_issuer": _ISSUER,
        }
        for key, value in values.items():
            object.__setattr__(self, key, value)

    def __setattr__(self, name, value):
        raise AttributeError("Verified candidate profile is immutable")

    @property
    def model_revision(self):
        return self._model_bundle.revision

    @property
    def runtime_revision(self):
        return self._runtime_bundle.revision

    def is_current(self):
        """Fast metadata recheck, not proof against same-user code compromise."""
        return (
            self._issuer is _ISSUER
            and self._model_bundle.is_current()
            and self._runtime_bundle.is_current()
        )


def _verified_arm64_binary(root, name, expected_sha256, family):
    """Hash an allowlisted executable and reject non-AArch64 or unsafe ELF."""
    runtime = verify_stt_model_files(
        root, family=family, expected_sha256={name: expected_sha256},
    )
    try:
        path = Path(runtime.root) / name
        metadata = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(metadata.st_mode)
                or not metadata.st_mode & 0o111
                or metadata.st_mode & 0o6000
                or not 64 <= metadata.st_size <= _MAX_RUNTIME_BYTES):
            raise ValueError
        # Only inspect a constant-size ELF header. Do not execute or dlopen.
        with path.open("rb") as stream:
            header = stream.read(64)
        if (
            len(header) != 64 or header[:4] != b"\x7fELF"
            or header[4:7] != b"\x02\x01\x01"
            or int.from_bytes(header[16:18], "little") not in (2, 3)
            or int.from_bytes(header[18:20], "little") != _ARM64_MACHINE
            or not runtime.is_current()
        ):
            raise ValueError
        return runtime
    except (OSError, ValueError, TypeError):
        raise ValueError("Untrusted ARM64 speech runtime") from None


def verify_candidate_profile(profile, *, model_root, model_sha256,
                             runtime_root, runtime_sha256):
    """Read-only offline attestation; cannot issue model votes or execute CLI."""
    if type(profile) is not str or profile not in _PROFILES:
        raise ValueError("Unsupported independent STT candidate")
    if (type(model_sha256) is not str or not _DIGEST.fullmatch(model_sha256)
            or type(runtime_sha256) is not str
            or not _DIGEST.fullmatch(runtime_sha256)):
        raise ValueError("Invalid candidate SHA256 manifest")
    if not isinstance(model_root, (str, Path)) or not isinstance(runtime_root, (str, Path)):
        raise ValueError("Invalid candidate model/runtime roots")
    family, engine, model_name, binary_name = _PROFILES[profile]
    model_bundle = verify_stt_model_files(
        model_root, family=family, expected_sha256={model_name: model_sha256},
    )
    runtime_bundle = _verified_arm64_binary(
        runtime_root, binary_name, runtime_sha256,
        "canary_runtime" if family == "canary" else "whisper_runtime",
    )
    result = VerifiedCandidateProfile(
        _ISSUER, profile=profile, family=family, engine=engine,
        model_file=model_name, runtime_file=binary_name,
        model_bundle=model_bundle, runtime_bundle=runtime_bundle,
    )
    if not result.is_current():
        raise ValueError("Candidate changed before attestation completed")
    return result


def verify_independent_candidates(manifests):
    """All-or-nothing readiness: one Canary and one Whisper; no partial set."""
    if (type(manifests) is not dict
            or set(manifests) != set(_PROFILES)):
        raise ValueError("Two distinct reviewed model families are required")
    verified = []
    for profile in _PROFILES:
        args = manifests[profile]
        if (type(args) is not dict
                or set(args) != {
                    "model_root", "model_sha256",
                    "runtime_root", "runtime_sha256",
                }):
            raise ValueError("Invalid independent STT manifest")
        verified.append(verify_candidate_profile(profile, **args))
    if not all(item.is_current() for item in verified):
        raise ValueError("Candidate files changed during verification")
    if verified[0].family == verified[1].family:
        raise ValueError("Independent STT families required")
    return tuple(verified)
