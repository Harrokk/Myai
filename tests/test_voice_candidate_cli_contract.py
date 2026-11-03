"""Pinned CLI contract tests; synthetic model bytes, no native execution."""
import hashlib
import json
import pytest

from core.voice_candidate_cli_contract import (
    candidate_cli_argv, parse_candidate_stdout,
)
from core.voice_candidate_preflight import verify_candidate_profile


PROFILES = {
    "canary-1b-v2-q8": ("canary-1b-v2-Q8_0.gguf", "transcribe-cli"),
    "whisper-large-v3-turbo": ("ggml-large-v3-turbo.bin", "whisper-cli"),
}


def profile(tmp_path, name):
    filename, executable = PROFILES[name]
    model = tmp_path / "model"
    binary = tmp_path / "runtime"
    model.mkdir()
    binary.mkdir()
    data = b"synthetic-only-model"
    elf = bytearray(64)
    elf[:7] = b"\x7fELF\x02\x01\x01"
    elf[16:18] = (3).to_bytes(2, "little")
    elf[18:20] = (183).to_bytes(2, "little")
    model_file = model / filename
    runtime_file = binary / executable
    model_file.write_bytes(data)
    runtime_file.write_bytes(bytes(elf))
    model_file.chmod(0o444)
    runtime_file.chmod(0o555)
    model.chmod(0o555)
    binary.chmod(0o555)
    return verify_candidate_profile(
        name, model_root=model,
        model_sha256=hashlib.sha256(data).hexdigest(),
        runtime_root=binary,
        runtime_sha256=hashlib.sha256(bytes(elf)).hexdigest(),
    )


def whisper_json(*, lang="swedish", configured="sv",
                 translate=False, segments=None):
    return json.dumps({
        "params": {"language": configured, "translate": translate},
        "result": {"language": lang},
        "transcription": (
            [{"text": " Hej"}, {"text": " världen"}]
            if segments is None else segments
        ),
    }).encode("utf-8")


def test_canary_fixed_args_are_cpu_swedish_transcription_only(tmp_path):
    p = profile(tmp_path, "canary-1b-v2-q8")
    argv = candidate_cli_argv(p, "/proc/self/fd/7", threads=2)
    assert argv == [
        str(tmp_path / "runtime" / "transcribe-cli"),
        "-q", "--backend", "cpu", "--timestamps", "none",
        "--threads", "2", "--task", "transcribe",
        "-m", str(tmp_path / "model" / "canary-1b-v2-Q8_0.gguf"),
        "-l", "sv", "/proc/self/fd/7",
    ]
    assert "--translate" not in argv


def test_whisper_fixed_args_use_stdout_json_and_cpu(tmp_path):
    p = profile(tmp_path, "whisper-large-v3-turbo")
    argv = candidate_cli_argv(p, "/proc/self/fd/15", threads=4)
    assert argv == [
        str(tmp_path / "runtime" / "whisper-cli"),
        "-np", "-nt", "-ng", "-t", "4",
        "-l", "sv", "-m",
        str(tmp_path / "model" / "ggml-large-v3-turbo.bin"),
        "-f", "/proc/self/fd/15", "-oj", "-of", "-",
    ]
    assert "-tr" not in argv


@pytest.mark.parametrize("bad", [
    "../../etc/shadow", "/tmp/speech.wav", "/proc/self/fd/-1",
    "/proc/self/fd/2;cat", "/proc/self/fd/1\n", None, 123,
])
def test_non_memfd_audio_paths_never_enter_native_argv(tmp_path, bad):
    p = profile(tmp_path, "canary-1b-v2-q8")
    with pytest.raises(ValueError):
        candidate_cli_argv(p, bad)


@pytest.mark.parametrize("count", [0, 5, -1, True, "2", 1.5])
def test_unreviewed_thread_count_denied(tmp_path, count):
    p = profile(tmp_path, "whisper-large-v3-turbo")
    with pytest.raises(ValueError):
        candidate_cli_argv(p, "/proc/self/fd/8", count)


def test_changed_model_cannot_build_native_command(tmp_path):
    p = profile(tmp_path, "canary-1b-v2-q8")
    file = tmp_path / "model" / "canary-1b-v2-Q8_0.gguf"
    file.chmod(0o644)
    with pytest.raises(ValueError):
        candidate_cli_argv(p, "/proc/self/fd/8")


def test_canary_single_exact_success_line_is_accepted():
    out = (
        b"audio: /proc/self/fd/8\n"
        b"  samples:    16000\n"
        b"run: ok\ntext: Hej v\xc3\xa4rlden.\n"
    )
    assert parse_candidate_stdout("canary-1b-v2-q8", out) == {
        "text": "Hej världen.", "language": "sv", "confidence": None,
    }


@pytest.mark.parametrize("bad", [
    b"run: unsupported language\ntext: hej\n",
    b"run: ok\ntext: hej\nrun: ok\n",
    b"run: ok\ntext: hej\ntext: annan\n",
    b"run: ok\ntext: (empty)\n  note: output truncated\n",
    b"run: ok\ntext: hej\n  note: output repetition\n",
    b"run: ok\ntext: hej\x1b[31m\n",
    b"run: ok\ntext: \xff\n",
    b"",
    b"x" * 32769,
])
def test_canary_does_not_vote_for_malformed_or_incomplete_output(bad):
    with pytest.raises(ValueError):
        parse_candidate_stdout("canary-1b-v2-q8", bad)


def test_whisper_json_segments_are_concatenated_without_timestamps():
    assert parse_candidate_stdout(
        "whisper-large-v3-turbo", whisper_json(),
    ) == {"text": "Hej världen", "language": "sv", "confidence": None}


@pytest.mark.parametrize("payload", [
    whisper_json(lang="english"),
    whisper_json(configured="en"),
    whisper_json(translate=True),
    whisper_json(segments=[]),
    whisper_json(segments=[{"text": {"tool": "remove"}}]),
    whisper_json(segments=[{"text": "\x00sneaky"}]),
    b'{"params":{"language":"sv","language":"sv","translate":false},'
    b'"result":{"language":"swedish"},"transcription":[{"text":"hej"}]}',
    whisper_json() + b"Extra native log",
])
def test_whisper_rejects_language_mismatch_injection_and_malformed_json(payload):
    with pytest.raises(ValueError):
        parse_candidate_stdout("whisper-large-v3-turbo", payload)


def test_profile_name_from_untrusted_model_output_does_not_select_parser():
    with pytest.raises(ValueError):
        parse_candidate_stdout("arbitrary-custom", whisper_json())
