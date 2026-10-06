from copy import deepcopy

import pytest

from core.config import DEFAULT_SETTINGS
from core.geniex_client import GenieXClient
from core.llm_factory import build_llm_client
from core.ollama_client import OllamaClient
from core.resilient_llm import ResilientLLMClient


def test_llm_factory_uses_ollama_by_default():
    settings = deepcopy(DEFAULT_SETTINGS)

    client = build_llm_client(settings)

    assert isinstance(client, OllamaClient)
    assert client.provider_name == "ollama"
    assert client.model == settings["ollama"]["model"]


def test_llm_factory_builds_geniex_client():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["llm"]["provider"] = "geniex"

    client = build_llm_client(settings)

    assert isinstance(client, GenieXClient)
    assert client.provider_name == "geniex"
    assert client.model == settings["geniex"]["model"]
    assert client.base_url == settings["geniex"]["base_url"]


def test_llm_factory_rejects_unknown_provider():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["llm"]["provider"] = "unknown"

    with pytest.raises(ValueError, match="Okänd LLM-provider"):
        build_llm_client(settings)



def test_llm_factory_builds_disabled_fallback_only_when_enabled():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["llm"]["provider"] = "geniex"

    client = build_llm_client(settings)

    assert isinstance(
        client,
        GenieXClient,
    )


def test_llm_factory_builds_geniex_local_fallback():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["llm"]["provider"] = "geniex"
    settings["llm"]["fallback"] = {
        "enabled": True,
        "provider": "geniex",
        "model": "fallback-model",
    }

    client = build_llm_client(settings)

    assert isinstance(
        client,
        ResilientLLMClient,
    )
    assert client.primary.model == settings["geniex"]["model"]
    assert client.fallback.model == "fallback-model"
    assert client.enabled is True


def test_llm_factory_requires_fallback_model_when_enabled():
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["llm"]["provider"] = "geniex"
    settings["llm"]["fallback"] = {
        "enabled": True,
        "provider": "geniex",
        "model": "",
    }

    with pytest.raises(
        ValueError,
        match="reservmodell",
    ):
        build_llm_client(settings)



def test_llm_factory_attaches_health_aware_policy(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["llm"]["provider"] = "geniex"
    settings["llm"]["fallback"] = {
        "enabled": True,
        "provider": "geniex",
        "model": "fallback-model",
        "health_aware": {
            "enabled": True,
            "failure_threshold": 3,
            "recovery_success_threshold": 3,
        },
    }

    client = build_llm_client(
        settings,
        project_root=tmp_path,
    )

    assert isinstance(
        client,
        ResilientLLMClient,
    )
    assert client.backend_policy is not None
    assert client.backend_policy.enabled is True
    assert client.backend_policy.project_root == tmp_path
