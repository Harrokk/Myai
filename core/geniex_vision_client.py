import base64
import mimetypes
from pathlib import Path

import requests


class GenieXVisionClient:
    provider_name = "geniex"

    def __init__(
        self,
        base_url,
        model,
        enabled=False,
        api_key="geniex",
        max_tokens=256,
        temperature=0.2,
    ):
        self.base_url = base_url.rstrip("/")
        self.url = f"{self.base_url}/chat/completions"
        self.model = model
        self.enabled = bool(enabled)
        self.api_key = api_key or "geniex"
        self.max_tokens = max(1, int(max_tokens))
        self.temperature = float(temperature)

    def _validate_ready(self):
        if not self.enabled:
            raise RuntimeError(
                "Visionanalys är avstängd i konfigurationen."
            )

        if not self.model:
            raise RuntimeError(
                "Ingen visionmodell är konfigurerad."
            )

    @staticmethod
    def _data_url(data, mime_type):
        encoded = base64.b64encode(
            bytes(data)
        ).decode("ascii")

        return (
            f"data:{mime_type};base64,"
            f"{encoded}"
        )

    def _request_urls(
        self,
        image_urls,
        prompt,
        timeout=120,
    ):
        self._validate_ready()

        if not image_urls:
            raise ValueError(
                "Minst en bild krävs för visionanalys."
            )

        content = [
            {
                "type": "text",
                "text": str(prompt),
            }
        ]

        content.extend(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url,
                },
            }
            for image_url in image_urls
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False,
        }

        response = requests.post(
            self.url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": (
                    f"Bearer {self.api_key}"
                ),
            },
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

        try:
            answer = (
                data["choices"][0]
                ["message"]["content"]
            )
        except (
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            raise ValueError(
                "GenieX VLM-svaret saknar "
                "choices[0].message.content."
            ) from error

        if not isinstance(answer, str):
            raise ValueError(
                "GenieX VLM-svaret måste vara text."
            )

        return answer

    def analyze(
        self,
        image_path,
        prompt,
        timeout=120,
    ):
        return self.analyze_images(
            [image_path],
            prompt,
            timeout=timeout,
        )

    def analyze_images(
        self,
        image_paths,
        prompt,
        timeout=120,
    ):
        self._validate_ready()
        paths = [
            Path(path)
            for path in image_paths
        ]

        if not paths:
            raise ValueError(
                "Minst en bild krävs för visionanalys."
            )

        urls = []

        for path in paths:
            if (
                not path.exists()
                or not path.is_file()
            ):
                raise FileNotFoundError(
                    f"Bildfilen finns inte: {path}"
                )

            mime_type = (
                mimetypes.guess_type(
                    path.name
                )[0]
                or "image/jpeg"
            )
            urls.append(
                self._data_url(
                    path.read_bytes(),
                    mime_type,
                )
            )

        return self._request_urls(
            urls,
            prompt,
            timeout=timeout,
        )

    def analyze_bytes(
        self,
        images,
        prompt,
        timeout=120,
    ):
        self._validate_ready()
        values = list(images)

        if not values:
            raise ValueError(
                "Minst en bild krävs för visionanalys."
            )

        urls = []

        for image in values:
            if (
                not isinstance(
                    image,
                    (
                        bytes,
                        bytearray,
                        memoryview,
                    ),
                )
                or not image
            ):
                raise ValueError(
                    "Bilddata för visionanalys måste "
                    "vara icke-tomma bytes."
                )

            urls.append(
                self._data_url(
                    image,
                    "image/jpeg",
                )
            )

        return self._request_urls(
            urls,
            prompt,
            timeout=timeout,
        )
