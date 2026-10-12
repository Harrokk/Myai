"""Optional local Ollama/GenieX response backend for staged VENTUNO voice.

No server starts, model downloads, audio access, configuration writes, or
automatic fallback. Works with existing MyAI LLM provider factory. GenieX
remains the active default in production. Caller explicitly selects Ollama.
"""
from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlparse

from core.config import DEFAULT_SETTINGS, _merge_settings
from core.config_validation import validate_settings
from core.llm_factory import build_llm_client
from scripts.ventuno_usb_dialogue_once import (
    approved_short_question, clean_reply,
)

ALLOWED_PROVIDERS = frozenset(("geniex", "ollama"))
OLLAMA_MODEL = "qwen3:0.6b"
OLLAMA_LOCAL_URL = "http://127.0.0.1:11434/api/chat"


def select_isolated_voice_client(profile: object, *, provider: str):
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError("unsupported-voice-backend")
    if not isinstance(profile, dict):
        raise ValueError("invalid-voice-backend-profile")
    # Never mutate caller profile, active configuration or global defaults.
    settings = _merge_settings(DEFAULT_SETTINGS, deepcopy(profile))
    if settings.get("llm", {}).get("provider") != "geniex":
        raise ValueError("ventuno-production-must-remain-geniex")
    if settings["llm"].get("fallback", {}).get("enabled") is not False:
        raise ValueError("automatic-model-fallback-must-remain-disabled")
    if settings.get("voice", {}).get("enabled") is not False:
        raise ValueError("production-voice-must-remain-disabled")
    if provider == "ollama":
        ollama = settings.get("ollama", {})
        if ollama.get("model") != OLLAMA_MODEL:
            raise ValueError("unapproved-small-ollama-model")
        url = ollama.get("url")
        if url != OLLAMA_LOCAL_URL:
            raise ValueError("ollama-must-be-strict-local-loopback")
    else:
        base = settings.get("geniex", {}).get("base_url", "")
        parsed = urlparse(str(base))
        if parsed.scheme != "http" or parsed.hostname not in (
            "127.0.0.1", "localhost", "::1",
        ):
            raise ValueError("geniex-must-be-local-loopback")

    # Validate the in-memory selected configuration; do NOT write it back.
    settings["llm"]["provider"] = provider
    if not validate_settings(settings, require_ventuno_profile=True)["valid"]:
        raise ValueError("invalid-selected-voice-backend-config")
    client = build_llm_client(settings)
    if getattr(client, "provider_name", "") != provider:
        raise ValueError("wrong-local-provider-selected")
    return client


def answer_one_short_voice_question(
    question: object, profile: object, *, provider: str = "geniex",
    timeout: int = 80,
) -> str:
    canonical = approved_short_question(question)
    if canonical is None or canonical != question:
        raise ValueError("unapproved-voice-question")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 90:
        raise ValueError("invalid-voice-response-timeout")
    client = select_isolated_voice_client(profile, provider=provider)
    response = client.chat(
        [
            {"role": "system", "content":
             "Du är MyAI. Svara kort på svenska med högst sex ord. "
             "Inga verktyg, inga systemändringar."},
            {"role": "user", "content": canonical},
        ],
        timeout=timeout,
    )
    result = clean_reply(response)
    if result is None:
        raise ValueError("unbounded-or-invalid-voice-reply")
    return result
