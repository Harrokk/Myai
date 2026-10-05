from core.geniex_client import GenieXClient
from core.ollama_client import OllamaClient
from core.resilient_llm import ResilientLLMClient


def _build_provider(
    settings,
    provider,
    model_override=None,
):
    name = str(
        provider
        or ""
    ).strip().lower()

    if name == "ollama":
        config = settings["ollama"]
        return OllamaClient(
            config["url"],
            (
                model_override
                or config["model"]
            ),
        )

    if name == "geniex":
        config = settings["geniex"]
        return GenieXClient(
            config["base_url"],
            (
                model_override
                or config["model"]
            ),
            api_key=config.get(
                "api_key",
                "geniex",
            ),
            max_tokens=config.get(
                "max_tokens",
                256,
            ),
            temperature=config.get(
                "temperature",
                0.4,
            ),
            enable_think=config.get(
                "enable_think",
                False,
            ),
        )

    raise ValueError(
        f"Okänd LLM-provider: {name}. "
        "Tillåtna värden är ollama och geniex."
    )


def build_llm_client(settings):
    """Skapa vald lokal LLM-provider och valfri lokal fallback."""

    llm = settings.get(
        "llm",
        {},
    )
    provider = str(
        llm.get(
            "provider",
            "ollama",
        )
    ).strip().lower()

    primary = _build_provider(
        settings,
        provider,
    )

    fallback = llm.get(
        "fallback",
        {},
    )
    fallback_enabled = bool(
        fallback.get(
            "enabled",
            False,
        )
    )

    if not fallback_enabled:
        return primary

    fallback_provider = str(
        fallback.get(
            "provider",
            provider,
        )
    ).strip().lower()
    fallback_model = str(
        fallback.get(
            "model",
            "",
        )
        or ""
    ).strip()

    if not fallback_model:
        raise ValueError(
            "LLM-fallback är aktiverad men ingen reservmodell är konfigurerad."
        )

    fallback_client = _build_provider(
        settings,
        fallback_provider,
        model_override=fallback_model,
    )

    return ResilientLLMClient(
        primary,
        fallback=fallback_client,
        enabled=True,
    )
