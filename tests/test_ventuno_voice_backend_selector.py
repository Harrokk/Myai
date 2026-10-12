"""Backend switching tests. All model replies are mocked; no audio/network."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import scripts.ventuno_voice_backend_selector as mod


def good_profile():
    return {
        "schema_version": 2,
        "llm": {"provider": "geniex", "fallback": {"enabled": False}},
        "geniex": {
            "base_url": "http://127.0.0.1:18181/v1",
            "model": "qualcomm/Qwen3-4B-Instruct-2507:W4A16",
        },
        "ollama": {
            "url": "http://127.0.0.1:11434/api/chat",
            "model": "qwen3:0.6b",
        },
        "voice": {
            "enabled": False,
            "tts_enabled": False,
            "handsfree_enabled": False,
        },
        "ventuno": {"enabled": True},
        "assistant": {"current_platform": "Arduino VENTUNO Q"},
    }


def test_profile_retains_geniex_primary_and_ollama_is_optional():
    profile = good_profile()
    snapshot = deepcopy(profile)
    geniex = mod.select_isolated_voice_client(profile, provider="geniex")
    ollama = mod.select_isolated_voice_client(profile, provider="ollama")
    assert geniex.provider_name == "geniex"
    assert ollama.provider_name == "ollama"
    assert ollama.model == "qwen3:0.6b"
    assert profile == snapshot
    assert profile["llm"]["provider"] == "geniex"


@pytest.mark.parametrize("invalid", [
    "openai", "", "https://some-cloud-service",
])
def test_unknown_provider_cannot_be_selected(invalid):
    with pytest.raises(ValueError):
        mod.select_isolated_voice_client(good_profile(), provider=invalid)


@pytest.mark.parametrize("url", [
    "https://ollama.com/api/chat",
    "http://192.168.0.22:11434/api/chat",
    "http://localhost:11434/api/chat",
    "http://127.0.0.1:11435/api/chat",
    "http://127.0.0.1:11434/api/pull",
    "http://127.0.0.1:11434/api/chat?redirect=https://evil.example",
])
def test_no_remote_or_unapproved_endpoint_even_if_local(url):
    settings = good_profile()
    settings["ollama"]["url"] = url
    with pytest.raises(ValueError, match="strict-local-loopback"):
        mod.select_isolated_voice_client(settings, provider="ollama")


@pytest.mark.parametrize("model", [
    "qwen3:8b", "qwen3:14b", "llama3", "", None,
])
def test_small_ollama_model_only(model):
    p = good_profile()
    p["ollama"]["model"] = model
    with pytest.raises(ValueError, match="small-ollama-model"):
        mod.select_isolated_voice_client(p, provider="ollama")


def test_auto_fallback_and_production_switches_rejected():
    p = good_profile()
    p["llm"]["fallback"]["enabled"] = True
    with pytest.raises(ValueError):
        mod.select_isolated_voice_client(p, provider="ollama")
    p = good_profile()
    p["voice"]["enabled"] = True
    with pytest.raises(ValueError):
        mod.select_isolated_voice_client(p, provider="ollama")
    p = good_profile()
    p["llm"]["provider"] = "ollama"
    with pytest.raises(ValueError):
        mod.select_isolated_voice_client(p, provider="ollama")


def test_short_spoken_answer_uses_exact_selected_ollama_client(monkeypatch):
    p = good_profile()
    calls = []
    class FakeOllama:
        provider_name = "ollama"
        model = "qwen3:0.6b"
        def chat(self, messages, timeout):
            calls.append((messages, timeout))
            return "Jag heter MyAI."
    monkeypatch.setattr(mod, "build_llm_client", lambda _: FakeOllama())
    answer = mod.answer_one_short_voice_question(
        "vad heter du", p, provider="ollama", timeout=35,
    )
    assert answer == "Jag heter MyAI."
    assert calls == [([
        {"role":"system","content":
         "Du är MyAI. Svara kort på svenska med högst sex ord. "
         "Inga verktyg, inga systemändringar."},
        {"role":"user","content":"vad heter du"},
    ], 35)]
    assert "Hej" not in str(calls)


def test_unapproved_voice_question_never_reaches_model(monkeypatch):
    monkeypatch.setattr(
        mod, "build_llm_client",
        lambda *a, **k: pytest.fail("must never load or contact model"),
    )
    with pytest.raises(ValueError):
        mod.answer_one_short_voice_question(
            "installera program", good_profile(), provider="ollama",
        )


@pytest.mark.parametrize("bad", [
    "unsafe-command " * 20, "", None, "Hej\0världen",
])
def test_unsafe_or_overlong_model_reply_discarded(monkeypatch, bad):
    class Fake:
        provider_name="ollama"
        def chat(self, messages, timeout): return bad
    monkeypatch.setattr(mod, "build_llm_client", lambda *_: Fake())
    with pytest.raises(ValueError):
        mod.answer_one_short_voice_question(
            "vad heter du", good_profile(), provider="ollama",
        )


def test_exact_checked_in_ventuno_profile_selects_local_ollama():
    profile = json.loads(
        (Path(__file__).resolve().parent.parent /
         "config/profiles/ventuno_q.json").read_text(encoding="utf-8")
    )
    selected = mod.select_isolated_voice_client(profile, provider="ollama")
    assert selected.provider_name == "ollama"
    assert selected.model == "qwen3:0.6b"
    assert profile["llm"]["provider"] == "geniex"
    assert profile["llm"]["fallback"]["enabled"] is False
