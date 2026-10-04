import json

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

    def chat_stream(self, messages, timeout=300):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        response = requests.post(
            self.url,
            json=payload,
            timeout=timeout,
            stream=True,
        )
        response.raise_for_status()

        try:
            for raw_line in response.iter_lines(
                decode_unicode=True,
            ):
                if isinstance(raw_line, bytes):
                    line = raw_line.decode(
                        "utf-8",
                        errors="replace",
                    )
                else:
                    line = str(raw_line or "")

                line = line.strip()

                if not line:
                    continue

                try:
                    data = json.loads(line)
                    content = (
                        data.get("message", {})
                        .get("content")
                    )
                except (
                    json.JSONDecodeError,
                    TypeError,
                ) as error:
                    raise ValueError(
                        "Ogiltigt streaming-svar från Ollama."
                    ) from error

                if content:
                    yield str(content)

                if data.get("done"):
                    break
        finally:
            close = getattr(
                response,
                "close",
                None,
            )

            if callable(close):
                close()
