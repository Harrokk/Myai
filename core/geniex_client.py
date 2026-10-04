import requests


class GenieXClient:
    """Minimal OpenAI-compatible client for Qualcomm GenieX local server."""

    provider_name = "geniex"

    def __init__(
        self,
        base_url,
        model,
        api_key="geniex",
    ):
        self.base_url = base_url.rstrip("/")
        self.url = f"{self.base_url}/chat/completions"
        self.model = model
        self.api_key = api_key or "geniex"

    def chat(self, messages, timeout=300):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        response = requests.post(
            self.url,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()

        data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError(
                "GenieX-svaret saknar choices[0].message.content."
            ) from error

        if not isinstance(content, str):
            raise ValueError(
                "GenieX-svarets message.content måste vara text."
            )

        return content
