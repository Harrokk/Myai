"""Bounded sequential GenieX throughput benchmark (no extra model instance).

This measures the served model via the existing OpenAI-compatible API.
It does NOT measure HTP utilization, HTP cycles or per-layer latency.
"""

from __future__ import annotations

import json
import statistics
import time
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:18181/v1"


def numeric_timing(result: dict) -> dict[str, float]:
    metrics = result.get("timings")
    if not isinstance(metrics, dict):
        return {}
    result_map: dict[str, float] = {}
    for name in (
        "prompt_n", "prompt_ms", "prompt_per_second",
        "predicted_n", "predicted_ms", "predicted_per_second",
    ):
        value = metrics.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value >= 0 and value < 1e10:
                result_map[name] = round(float(value), 2)
    return result_map


def aggregate_timings(samples: list[dict[str, float]]) -> dict[str, float]:
    result = {}
    for field in ("prompt_per_second", "predicted_per_second"):
        values = [s[field] for s in samples if s.get(field, 0) > 0
                  and (field != "predicted_per_second" or s.get("predicted_n", 0) >= 16)]
        if values:
            result["median_" + field] = round(statistics.median(values), 2)
    return result


def main() -> int:
    with urlopen(BASE + "/models", timeout=12) as response:
        models = json.load(response).get("data", [])
    assert models and models[0].get("id"), "No active GenieX model"
    model = models[0]["id"]
    prompt = (
        "Skriv en sammanhängande svensk förklaring av hur en väderstation "
        "mäter temperatur, vind, lufttryck och luftfuktighet. "
        "Beskriv även varför mätvärden kan variera mellan dagar. "
        "Skriv minst tolv tydliga meningar."
    )
    samples = []
    for iteration in range(3):
        payload = json.dumps({
            "model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 128, "temperature": 0, "stream": False,
        }).encode("utf-8")
        request = Request(
            BASE + "/chat/completions", data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        start = time.monotonic()
        with urlopen(request, timeout=90) as response:
            data = json.load(response)
        elapsed = time.monotonic() - start
        choices = data.get("choices") or []
        answer = str((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
        assert answer, f"Empty generation on iteration {iteration + 1}"
        timing = numeric_timing(data)
        timing["wall_seconds"] = round(elapsed, 2)
        samples.append(timing)
        print("Run", iteration + 1, json.dumps(timing, sort_keys=True))

    print("Median throughput:", json.dumps(aggregate_timings(samples), sort_keys=True))
    print("Test ran sequentially against existing service; no second model load.")
    print("These are model API timings, not measured NPU occupancy/cycles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
