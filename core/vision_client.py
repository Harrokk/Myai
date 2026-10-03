import base64
from pathlib import Path

import requests


class VisionClient:
    def __init__(self, url, model, enabled=False):
        self.url = url
        self.model = model
        self.enabled = bool(enabled)

    def analyze(self, image_path, prompt, timeout=120):
        if not self.enabled:
            raise RuntimeError("Visionanalys är avstängd i konfigurationen.")

        if not self.model:
            raise RuntimeError("Ingen visionmodell är konfigurerad.")

        path = Path(image_path)

        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Bildfilen finns inte: {path}")

        encoded = base64.b64encode(path.read_bytes()).decode("ascii")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [encoded],
                }
            ],
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
                "Visionmodellens svar saknar message.content."
            ) from error
