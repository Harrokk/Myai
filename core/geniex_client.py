import json

import requests


class GenieXClient:
    """OpenAI-compatible client for Qualcomm GenieX local server."""

    provider_name = "geniex"

    def __init__(
        self,
        base_url,
        model,
        api_key="geniex",
        max_tokens=256,
        temperature=0.4,
        enable_think=False,
    ):
        self.base_url = base_url.rstrip("/")
        self.url = f"{self.base_url}/chat/completions"
        self.model = model
        self.api_key = api_key or "geniex"
        self.max_tokens = max(1, int(max_tokens))
        self.temperature = float(temperature)
        self.enable_think = bool(enable_think)

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _payload(self, messages, stream):
        return {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "enable_think": self.enable_think,
            "stream": bool(stream),
        }

    def chat(self, messages, timeout=300):
        response = requests.post(
            self.url,
            json=self._payload(
                messages,
                stream=False,
            ),
            headers=self._headers(),
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

    def chat_stream(self, messages, timeout=300):
        response = requests.post(
            self.url,
            json=self._payload(
                messages,
                stream=True,
            ),
            headers=self._headers(),
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

                if not line or line.startswith(":"):
                    continue

                if not line.startswith("data:"):
                    continue

                payload = line[5:].strip()

                if payload == "[DONE]":
                    break

                try:
                    data = json.loads(payload)
                    content = (
                        data["choices"][0]
                        .get("delta", {})
                        .get("content")
                    )
                except (
                    json.JSONDecodeError,
                    KeyError,
                    IndexError,
                    TypeError,
                ) as error:
                    raise ValueError(
                        "Ogiltigt streaming-svar från GenieX."
                    ) from error

                if content:
                    yield str(content)
        finally:
            close = getattr(
                response,
                "close",
                None,
            )

            if callable(close):
                close()
