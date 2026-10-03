import requests


class FrankfurterClient:
    def __init__(
        self,
        base_url="https://api.frankfurter.app",
        timeout_seconds=10,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.timeout_seconds = float(timeout_seconds)

    def rate_to_sek(self, currency):
        source = (currency or "").strip().upper()

        if not source:
            raise ValueError("Valutakod saknas.")

        if source == "SEK":
            return {
                "base": "SEK",
                "target": "SEK",
                "rate": 1.0,
                "date": None,
                "provider": "identity",
            }

        if len(source) != 3 or not source.isalpha():
            raise ValueError("Valutakoden måste vara en ISO-liknande trebokstavskod.")

        if not self.base_url:
            raise ValueError("Ingen FX-adress är konfigurerad.")

        response = requests.get(
            self.base_url + "/latest",
            params={
                "from": source,
                "to": "SEK",
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
            raise ValueError("FX-svaret är inte ett JSON-objekt.")

        rates = payload.get("rates")

        if not isinstance(rates, dict):
            raise ValueError("FX-svaret saknar rates.")

        rate = rates.get("SEK")

        if isinstance(rate, bool) or not isinstance(
            rate,
            (int, float),
        ):
            raise ValueError("FX-svaret saknar giltig SEK-kurs.")

        if rate <= 0:
            raise ValueError("FX-kursen måste vara positiv.")

        return {
            "base": source,
            "target": "SEK",
            "rate": float(rate),
            "date": payload.get("date"),
            "provider": "frankfurter",
        }
