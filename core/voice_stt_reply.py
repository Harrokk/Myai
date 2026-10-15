"""Strict, private-safe decoder shared by all isolated STT IPC modes.

An isolated STT worker is a separate process; its stdout is untrusted
even if the worker executable was chosen from our allowlist. Never
coerce JSON strings/bools into confidence or accept contradictory keys.
This module has no model, audio, device, process or network imports.
"""
from __future__ import annotations

import json

MAX_STT_REPLY_BYTES = 8192
MAX_STT_TEXT_CHARS = 4096
VALID_STT_LANGUAGES = frozenset({"sv", "en"})
REPLY_KEYS = frozenset({"text", "language", "confidence"})


def decode_stt_reply(payload):
    """Accept only bounded UTF-8 and the precise STT result schema.

    Errors are deliberately constant; model output and JSON contents
    never appear in thrown exceptions or their exception chains.
    """
    if (type(payload) is not bytes
            or not 0 < len(payload) <= MAX_STT_REPLY_BYTES):
        raise ValueError("Invalid STT reply")

    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Invalid STT reply")
            result[key] = value
        return result

    def reject_constant(_token):
        raise ValueError("Invalid STT reply")

    try:
        decoded = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except (ValueError, UnicodeError, RecursionError, TypeError):
        raise ValueError("Invalid STT reply") from None

    if (type(decoded) is not dict
            or set(decoded) != REPLY_KEYS
            or type(decoded["text"]) is not str
            or len(decoded["text"]) > MAX_STT_TEXT_CHARS
            or type(decoded["language"]) is not str
            or decoded["language"] not in VALID_STT_LANGUAGES
            or decoded["confidence"] is not None):
        raise ValueError("Invalid STT reply")

    return decoded
