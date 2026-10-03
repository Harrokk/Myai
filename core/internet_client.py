import requests


class SearXNGClient:
    def __init__(
        self,
        base_url,
        timeout_seconds=15,
        language="sv-SE",
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.language = language or "sv-SE"

    def search(self, query, limit=5):
        query = (query or "").strip()

        if not query:
            raise ValueError("Sökfrågan är tom.")

        if not self.base_url:
            raise ValueError("Ingen SearXNG-adress är konfigurerad.")

        limit = max(1, min(int(limit), 10))
        response = requests.get(
            self.base_url + "/search",
            params={
                "q": query,
                "format": "json",
                "language": self.language,
            },
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": "MyAI/1.0 local-assistant",
                "Accept": "application/json",
            },
        )
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("SearXNG-svaret är inte ett JSON-objekt.")

        raw_results = payload.get("results", [])

        if not isinstance(raw_results, list):
            raise ValueError("SearXNG-svaret saknar en giltig result-lista.")

        normalized = []

        for item in raw_results:
            if not isinstance(item, dict):
                continue

            url = (item.get("url") or "").strip()

            if not url:
                continue

            title = (
                item.get("title")
                or item.get("url")
                or "Utan titel"
            )
            snippet = (
                item.get("content")
                or item.get("snippet")
                or ""
            )
            engines = item.get("engines") or []

            if isinstance(engines, str):
                engines = [engines]

            normalized.append(
                {
                    "title": str(title).strip(),
                    "url": url,
                    "snippet": str(snippet).strip(),
                    "engines": [
                        str(engine)
                        for engine in engines
                        if engine
                    ],
                    "published_date": (
                        item.get("publishedDate")
                        or item.get("published_date")
                        or None
                    ),
                }
            )

            if len(normalized) >= limit:
                break

        return normalized
