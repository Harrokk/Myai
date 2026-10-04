from copy import deepcopy

import pytest

from core.config import DEFAULT_SETTINGS
from core.geniex_client import GenieXClient
from core.llm_factory import build_llm_client
from core.ollama_client import OllamaClient


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
