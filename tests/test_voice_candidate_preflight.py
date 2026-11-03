"""GitHub-only source contracts for two independent candidate STT models.

No real model data, CLI execution, downloads, microphone or Ventuno usage.
The synthetic ELF header exercises CPU architecture gating only.
"""
import hashlib
import os

import pytest

from core.voice_candidate_preflight import (
    VerifiedCandidateProfile, verify_candidate_profile,
    verify_independent_candidates,
)
from core.voice_tier_identity import TrustedSTTBindings


_SPECS = {
    "canary-1b-v2-q8": ("canary-1b-v2-Q8_0.gguf", "transcribe-cli"),
    "whisper-large-v3-turbo": ("ggml-large-v3-turbo.bin", "whisper-cli"),
}


def elf(machine=183, cls=2, file_type=3):
    payload = bytearray(64)
    payload[:4] = b"\x7fELF"
    payload[4:7] = bytes((cls, 1, 1))
    payload[16:18] = file_type.to_bytes(2, "little")
    payload[18:20] = machine.to_bytes(2, "little")
    return bytes(payload)


def fixture(tmp_path, profile, *, machine=183, executable=True,
            raw_binary=None):
    name, binary = _SPECS[profile]
    model_root = tmp_path / (profile + "-model")
    runtime_root = tmp_path / (profile + "-runtime")
    model_root.mkdir()
    runtime_root.mkdir()
    model_bytes = ("synthetic-pinned-" + profile).encode()
    binary_bytes = elf(machine=machine) if raw_binary is None else raw_binary
    model_path = model_root / name
    runtime_path = runtime_root / binary
    model_path.write_bytes(model_bytes)
    runtime_path.write_bytes(binary_bytes)
    model_path.chmod(0o444)
    runtime_path.chmod(0o555 if executable else 0o444)
    model_root.chmod(0o555)
    runtime_root.chmod(0o555)
    return {
        "model_root": model_root,
        "model_sha256": hashlib.sha256(model_bytes).hexdigest(),
        "runtime_root": runtime_root,
        "runtime_sha256": hashlib.sha256(binary_bytes).hexdigest(),
    }


@pytest.mark.parametrize("profile,expected_family,expected_engine", [
    ("canary-1b-v2-q8", "canary", "transcribe_cpp"),
    ("whisper-large-v3-turbo", "whisper", "whisper_cpp"),
])
def test_real_hash_and_arm64_header_are_required_but_nothing_executes(
    tmp_path, profile, expected_family, expected_engine,
):
    args = fixture(tmp_path, profile)
    result = verify_candidate_profile(profile, **args)
    assert type(result) is VerifiedCandidateProfile
    assert result.family == expected_family
    assert result.engine == expected_engine
    assert result.is_current()
    assert result.model_revision.startswith("sha256:")
    assert result.runtime_revision.startswith("sha256:")
    assert not hasattr(result, "transcribe")
    assert not hasattr(result, "start")


def test_two_completely_different_families_produce_atomic_attestation(tmp_path):
    both = {
        profile: fixture(tmp_path, profile)
        for profile in _SPECS
    }
    profiles = verify_independent_candidates(both)
    assert len(profiles) == 2
    assert {v.family for v in profiles} == {"canary", "whisper"}
    assert all(v.is_current() for v in profiles)


def test_same_family_cannot_be_reused_as_second_voter(tmp_path):
    only = {"canary-1b-v2-q8": fixture(tmp_path, "canary-1b-v2-q8")}
    with pytest.raises(ValueError, match="Two distinct"):
        verify_independent_candidates(only)


def test_missing_candidate_has_no_partial_attestation(tmp_path):
    both = {key: fixture(tmp_path, key) for key in _SPECS}
    both["whisper-large-v3-turbo"]["runtime_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        verify_independent_candidates(both)


@pytest.mark.parametrize("profile", list(_SPECS))
def test_modified_model_file_blocks_candidate(tmp_path, profile):
    args = fixture(tmp_path, profile)
    verified = verify_candidate_profile(profile, **args)
    path = args["model_root"] / _SPECS[profile][0]
    path.chmod(0o644)
    path.write_bytes(b"tampered-weights")
    path.chmod(0o444)
    assert verified.is_current() is False
    with pytest.raises(ValueError):
        verify_candidate_profile(profile, **args)


@pytest.mark.parametrize("profile", list(_SPECS))
def test_modified_cli_binary_blocks_candidate(tmp_path, profile):
    args = fixture(tmp_path, profile)
    verified = verify_candidate_profile(profile, **args)
    path = args["runtime_root"] / _SPECS[profile][1]
    path.chmod(0o755)
    path.write_bytes(elf(machine=62))
    path.chmod(0o555)
    assert verified.is_current() is False
    with pytest.raises(ValueError):
        verify_candidate_profile(profile, **args)


@pytest.mark.parametrize("machine", [0, 3, 40, 62, 243])
def test_non_arm64_elf_architectures_are_rejected(tmp_path, machine):
    args = fixture(tmp_path, "canary-1b-v2-q8", machine=machine)
    with pytest.raises(ValueError, match="Untrusted ARM64"):
        verify_candidate_profile("canary-1b-v2-q8", **args)


def test_non_executable_runtime_is_rejected(tmp_path):
    args = fixture(tmp_path, "canary-1b-v2-q8", executable=False)
    with pytest.raises(ValueError, match="Untrusted ARM64"):
        verify_candidate_profile("canary-1b-v2-q8", **args)


@pytest.mark.parametrize("bytes_", [b"not-an-elf", b"\x00" * 64, b"#! /bin/bash"])
def test_shell_script_and_fake_elf_header_cannot_become_runtime(
    tmp_path, bytes_,
):
    args = fixture(tmp_path, "whisper-large-v3-turbo", raw_binary=bytes_)
    with pytest.raises(ValueError, match="Untrusted ARM64"):
        verify_candidate_profile("whisper-large-v3-turbo", **args)


def test_verified_profile_is_immutable(tmp_path):
    v = verify_candidate_profile(
        "whisper-large-v3-turbo",
        **fixture(tmp_path, "whisper-large-v3-turbo"),
    )
    with pytest.raises(AttributeError):
        v.family = "parakeet"


def test_user_cannot_construct_a_fake_verified_profile():
    with pytest.raises(ValueError, match="Untrusted"):
        VerifiedCandidateProfile(
            object(),
            profile="whisper-large-v3-turbo",
            family="whisper", engine="whisper_cpp",
            model_file="ggml-large-v3-turbo.bin", runtime_file="whisper-cli",
            model_bundle=None, runtime_bundle=None,
        )


def test_candidate_preflight_is_not_a_stt_vote(tmp_path):
    v = verify_candidate_profile(
        "canary-1b-v2-q8",
        **fixture(tmp_path, "canary-1b-v2-q8"),
    )
    with pytest.raises(ValueError, match="invalid-or-duplicate"):
        TrustedSTTBindings([
            {"key": "candidate", "provider": v, "bundle": v._model_bundle}
        ])


@pytest.mark.parametrize("bad", ["canary", "whisper", "qwen3", "", 0, None])
def test_unknown_family_or_profile_cannot_enable_stt(tmp_path, bad):
    args = fixture(tmp_path, "canary-1b-v2-q8")
    with pytest.raises(ValueError, match="Unsupported"):
        verify_candidate_profile(bad, **args)


def test_symlinked_runtime_is_rejected(tmp_path):
    args = fixture(tmp_path, "whisper-large-v3-turbo")
    root = args["runtime_root"]
    target = root / "whisper-cli"
    root.chmod(0o755)
    replacement = root / "backup"
    target.rename(replacement)
    target.symlink_to(replacement)
    root.chmod(0o555)
    with pytest.raises(ValueError):
        verify_candidate_profile("whisper-large-v3-turbo", **args)


def test_runtime_setuid_bit_is_rejected(tmp_path):
    args = fixture(tmp_path, "canary-1b-v2-q8")
    binary = args["runtime_root"] / "transcribe-cli"
    binary.chmod(0o4555)
    with pytest.raises(ValueError, match="Untrusted ARM64"):
        verify_candidate_profile("canary-1b-v2-q8", **args)


def test_manifest_cannot_choose_arbitrary_binary_or_model(tmp_path):
    args = fixture(tmp_path, "canary-1b-v2-q8")
    with pytest.raises(TypeError):
        verify_candidate_profile("canary-1b-v2-q8", **args, binary_name="bash")


def test_output_never_contains_model_audio_or_executable_paths(tmp_path):
    args = fixture(tmp_path, "canary-1b-v2-q8")
    args["runtime_sha256"] = "0" * 64
    with pytest.raises(ValueError) as e:
        verify_candidate_profile("canary-1b-v2-q8", **args)
    assert str(args["runtime_root"]) not in str(e.value)
