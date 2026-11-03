"""Allowlisted native Canary/Whisper CLI arguments and strict stdout parsing.

Source-only: this file does not execute a binary. It requires a verified
candidate profile from voice_candidate_preflight. A future native child
must re-attest the *actual* model and executable before execve.

CLI contracts inspected against transcribe.cpp examples/cli/main.cpp,
asr.cpp and whisper.cpp examples/cli/cli.cpp on 2026-11-03. Source pinning
and review of native dependent libraries remain production blockers.
"""
import json
from pathlib import Path
import re

from core.voice_candidate_preflight import VerifiedCandidateProfile


_MAX_STDOUT = 32768
_MAX_TEXT = 4096
_SAFE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CANARY_STATUS = re.compile(r"^run: (.+)$")
_CANARY_TEXT = re.compile(r"^text: (.*)$")


def candidate_cli_argv(profile, wav_path, threads=2):
    """Fixed parameters: Swedish source, CPU, transcription only, no writes."""
    if (type(profile) is not VerifiedCandidateProfile
            or not profile.is_current()
            or type(wav_path) is not str
            or not re.fullmatch(r"/proc/self/fd/[0-9]{1,8}", wav_path)
            or type(threads) is not int or not 1 <= threads <= 4):
        raise ValueError("Invalid native candidate arguments")
    model = str(Path(profile.model_root) / profile.model_file)
    binary = str(Path(profile.runtime_root) / profile.runtime_file)
    if profile.profile == "canary-1b-v2-q8":
        return [
            binary, "-q", "--backend", "cpu", "--timestamps", "none",
            "--threads", str(threads), "--task", "transcribe",
            "-m", model, "-l", "sv", wav_path,
        ]
    if profile.profile == "whisper-large-v3-turbo":
        return [
            binary, "-np", "-nt", "-ng", "-t", str(threads),
            "-l", "sv", "-m", model, "-f", wav_path,
            "-oj", "-of", "-",
        ]
    raise ValueError("Unsupported native candidate profile")


def _clean_text(value):
    if (type(value) is not str or not 0 < len(value) <= _MAX_TEXT
            or _SAFE_CONTROL.search(value)
            or not value.strip()):
        raise ValueError("Unsafe native STT transcript")
    return " ".join(value.split())


def parse_candidate_stdout(profile_name, stdout):
    """No loose 'best effort' parser: unknown formats can NEVER be votes.

    Fail closed on stderr-only/error output, truncation, language mismatch,
    duplicate candidate fields, excess text and malformed native responses.
    """
    if (type(profile_name) is not str
            or profile_name not in ("canary-1b-v2-q8",
                                    "whisper-large-v3-turbo")
            or type(stdout) is not bytes
            or not 0 < len(stdout) <= _MAX_STDOUT):
        raise ValueError("Invalid native STT result")
    try:
        output = stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ValueError("Invalid native STT UTF-8") from None
    if _SAFE_CONTROL.search(output):
        raise ValueError("Unsafe native STT output")

    if profile_name == "canary-1b-v2-q8":
        # transcribe.cpp single-file mode emits setup, 'run: ok', then
        # 'text: TEXT'. Reject any partial/truncated/translated output.
        status = []
        texts = []
        for line in output.splitlines():
            match = _CANARY_STATUS.fullmatch(line)
            if match:
                status.append(match.group(1))
            match = _CANARY_TEXT.fullmatch(line)
            if match:
                texts.append(match.group(1))
            if ("note:" in line or "truncated" in line.casefold()
                    or "output repetition" in line.casefold()):
                raise ValueError("Incomplete native Canary transcript")
        if len(status) != 1 or status[0] != "ok" or len(texts) != 1:
            raise ValueError("Unverified native Canary response")
        text = _clean_text(texts[0])
    else:
        def reject_duplicate(keys):
            result = {}
            for k, v in keys:
                if k in result:
                    raise ValueError("Duplicate native Whisper JSON key")
                result[k] = v
            return result
        try:
            data = json.loads(output, object_pairs_hook=reject_duplicate)
        except (ValueError, TypeError, json.JSONDecodeError):
            raise ValueError("Invalid native Whisper JSON") from None
        if type(data) is not dict:
            raise ValueError("Invalid native Whisper root")
        meta = data.get("params")
        result = data.get("result")
        segments = data.get("transcription")
        if (type(meta) is not dict or meta.get("language") != "sv"
                or meta.get("translate") is not False
                or type(result) is not dict
                or result.get("language") not in ("swedish", "sv")
                or type(segments) is not list
                or not 0 < len(segments) <= 128):
            raise ValueError("Unverified native Whisper language or structure")
        items = []
        for segment in segments:
            if type(segment) is not dict:
                raise ValueError("Unverified native Whisper segment")
            items.append(_clean_text(segment.get("text")))
        text = _clean_text(" ".join(items))
    return {"text": text, "language": "sv", "confidence": None}
