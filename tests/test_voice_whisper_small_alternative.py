"""The smaller Whisper is an alternative family member, NOT a third vote."""
import hashlib
import json

import pytest

from core.voice_candidate_hosted_releases import hosted_model_release
from core.voice_candidate_cli_contract import candidate_cli_argv, parse_candidate_stdout
from core.voice_candidate_preflight import (
    verify_candidate_profile, verify_independent_candidates,
)


_SPECS = {
    "canary-1b-v2-q8": ("canary-1b-v2-Q8_0.gguf", "transcribe-cli"),
    "whisper-large-v3-turbo": ("ggml-large-v3-turbo.bin", "whisper-cli"),
    "whisper-small-q5_1": ("ggml-small-q5_1.bin", "whisper-cli"),
}


def fake_profile(tmp_path, profile):
    model_filename, binary_filename = _SPECS[profile]
    root = tmp_path / profile
    models = root / "model"
    binaries = root / "runtime"
    models.mkdir(parents=True)
    binaries.mkdir()
    data = ("fixture:" + profile).encode()
    elf = bytearray(64)
    elf[:7] = b"\x7fELF\x02\x01\x01"
    elf[16:18] = (3).to_bytes(2, "little")
    elf[18:20] = (183).to_bytes(2, "little")
    model = models / model_filename
    native = binaries / binary_filename
    model.write_bytes(data)
    native.write_bytes(bytes(elf))
    model.chmod(0o444)
    native.chmod(0o555)
    models.chmod(0o555)
    binaries.chmod(0o555)
    kwargs = dict(
        model_root=models, model_sha256=hashlib.sha256(data).hexdigest(),
        runtime_root=binaries,
        runtime_sha256=hashlib.sha256(bytes(elf)).hexdigest(),
    )
    return kwargs, verify_candidate_profile(profile, **kwargs)


def test_pinned_small_multilingual_release_is_190mb_and_is_whisper():
    release = hosted_model_release("whisper-small-q5_1")
    assert release.family == "whisper"
    assert release.filename == "ggml-small-q5_1.bin"
    assert release.bytes == 190085487
    assert release.sha256 == (
        "ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb"
    )
    assert "/resolve/main/" not in release.url
    assert release.license == "mit"


def test_small_cli_uses_same_swedish_cpu_only_native_runtime(tmp_path):
    args, profile = fake_profile(tmp_path, "whisper-small-q5_1")
    argv = candidate_cli_argv(profile, "/proc/self/fd/8")
    assert argv[0].endswith("/whisper-cli")
    assert "-ng" in argv
    assert argv[argv.index("-l") + 1] == "sv"
    assert argv[argv.index("-m") + 1].endswith("/ggml-small-q5_1.bin")
    assert argv[-3:] == ["-oj", "-of", "-"]


def test_whisper_small_uses_same_strict_json_parser():
    content = json.dumps({
        "params": {"language": "sv", "translate": False},
        "result": {"language": "swedish"},
        "transcription": [{"text": " Hej Sverige"}],
    }).encode()
    assert parse_candidate_stdout(
        "whisper-small-q5_1", content,
    )["text"] == "Hej Sverige"


def test_canary_plus_whisper_small_are_distinct_families(tmp_path):
    ca, _ = fake_profile(tmp_path, "canary-1b-v2-q8")
    sm, _ = fake_profile(tmp_path, "whisper-small-q5_1")
    records = verify_independent_candidates({
        "canary-1b-v2-q8": ca,
        "whisper-small-q5_1": sm,
    })
    assert {r.family for r in records} == {"canary", "whisper"}


def test_large_and_small_whisper_never_count_as_independent_votes(tmp_path):
    sm, _ = fake_profile(tmp_path, "whisper-small-q5_1")
    lg, _ = fake_profile(tmp_path, "whisper-large-v3-turbo")
    with pytest.raises(ValueError, match="Independent STT families"):
        verify_independent_candidates({
            "whisper-small-q5_1": sm, "whisper-large-v3-turbo": lg,
        })


def test_three_profiles_not_allowed_as_two_family_ready_bundle(tmp_path):
    records = {
        key: fake_profile(tmp_path, key)[0]
        for key in _SPECS
    }
    with pytest.raises(ValueError, match="Two distinct"):
        verify_independent_candidates(records)


def test_tampered_small_model_fails_before_any_native_execution(tmp_path):
    kwargs, profile = fake_profile(tmp_path, "whisper-small-q5_1")
    file = kwargs["model_root"] / "ggml-small-q5_1.bin"
    file.chmod(0o644)
    with pytest.raises(ValueError):
        candidate_cli_argv(profile, "/proc/self/fd/8")
