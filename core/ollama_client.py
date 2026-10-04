import requests


class OllamaClient:
    provider_name = "ollama"

    def __init__(self, url, model):
        self.url = url
        self.model = model

    def chat(self, messages, timeout=300):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        response = requests.post(
            self.url,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()

        data = response.json()

        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as error:
            raise ValueError(
                "Ollama-svaret saknar message.content."
            ) from error
