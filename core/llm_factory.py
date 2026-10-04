from core.geniex_client import GenieXClient
from core.ollama_client import OllamaClient


def build_llm_client(settings):
    """Skapa vald lokal LLM-provider utan att resten av MyAI behöver känna till den."""

    provider = (
        settings.get("llm", {})
        .get("provider", "ollama")
        .strip()
        .lower()
    )

    if provider == "ollama":
        config = settings["ollama"]
        return OllamaClient(
            config["url"],
            config["model"],
        )

    if provider == "geniex":
        config = settings["geniex"]
        return GenieXClient(
            config["base_url"],
            config["model"],
            api_key=config.get("api_key", "geniex"),
        )

    raise ValueError(
        f"Okänd LLM-provider: {provider}. "
        "Tillåtna värden är ollama och geniex."
    )
