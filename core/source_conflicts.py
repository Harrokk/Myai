import re
from urllib.parse import urlparse


NUMBER_UNIT_PATTERN = re.compile(
    r"(?P<value>-?\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>%|percent|procent|v|volt|a|ampere|w|watt|"
    r"°c|celsius|kg|g|mg|km|m|cm|mm|sek|kr|usd|eur)",
    flags=re.IGNORECASE,
)

UNIT_ALIASES = {
    "percent": "%",
    "procent": "%",
    "volt": "v",
    "ampere": "a",
    "watt": "w",
    "celsius": "°c",
    "kr": "sek",
}

STOPWORDS = {
    "och", "eller", "att", "det", "den", "som", "för", "med", "från",
    "till", "är", "var", "the", "and", "or", "for", "with", "from",
    "was", "were", "under", "measured",
}


def _host(url):
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def _tokens(text):
    tokens = re.findall(
        r"[a-zåäö0-9][a-zåäö0-9_-]{2,}",
        (text or "").lower(),
    )

    return {
        token
        for token in tokens
        if token not in STOPWORDS and not token.isdigit()
    }


def _numeric_claims(text):
    claims = []

    for match in NUMBER_UNIT_PATTERN.finditer(text or ""):
        raw_value = match.group("value").replace(",", ".")

        try:
            value = float(raw_value)
        except ValueError:
            continue

        raw_unit = match.group("unit").lower()
        unit = UNIT_ALIASES.get(raw_unit, raw_unit)
        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)
        context = text[start:end]

        claims.append(
            {
                "value": value,
                "unit": unit,
                "context": context.strip(),
                "tokens": _tokens(context),
            }
        )

    return claims


def _context_similarity(first, second):
    union = first["tokens"] | second["tokens"]

    if not union:
        return 0.0

    return len(first["tokens"] & second["tokens"]) / len(union)


def _candidate_text(candidate):
    return (
        candidate.get("page_text")
        or (
            (candidate.get("title") or "")
            + " "
            + (candidate.get("snippet") or "")
        )
    )


def detect_numeric_conflicts(
    candidates,
    relative_tolerance=0.05,
    context_threshold=0.25,
):
    conflicts = []

    for index, first in enumerate(candidates):
        first_host = _host(first.get("url"))
        first_claims = _numeric_claims(_candidate_text(first))

        for second in candidates[index + 1:]:
            second_host = _host(second.get("url"))

            if not first_host or not second_host or first_host == second_host:
                continue

            second_claims = _numeric_claims(_candidate_text(second))

            for first_claim in first_claims:
                for second_claim in second_claims:
                    if first_claim["unit"] != second_claim["unit"]:
                        continue

                    similarity = _context_similarity(
                        first_claim,
                        second_claim,
                    )

                    if similarity < context_threshold:
                        continue

                    denominator = max(
                        abs(first_claim["value"]),
                        abs(second_claim["value"]),
                        1e-9,
                    )
                    relative_difference = (
                        abs(
                            first_claim["value"]
                            - second_claim["value"]
                        )
                        / denominator
                    )

                    if relative_difference <= relative_tolerance:
                        continue

                    conflicts.append(
                        {
                            "first_url": first.get("url"),
                            "second_url": second.get("url"),
                            "first_value": first_claim["value"],
                            "second_value": second_claim["value"],
                            "unit": first_claim["unit"],
                            "context_similarity": round(similarity, 3),
                            "relative_difference": round(
                                relative_difference,
                                3,
                            ),
                        }
                    )

    return conflicts


def apply_conflict_penalties(
    candidates,
    conflicts,
    penalty_per_conflict=10.0,
):
    affected = {}

    for conflict in conflicts:
        affected[conflict["first_url"]] = (
            affected.get(conflict["first_url"], 0) + 1
        )
        affected[conflict["second_url"]] = (
            affected.get(conflict["second_url"], 0) + 1
        )

    adjusted = []

    for candidate in candidates:
        item = dict(candidate)
        count = affected.get(candidate.get("url"), 0)
        warnings = list(item.get("warning_flags") or [])

        if count:
            penalty = min(float(penalty_per_conflict) * count, 30.0)
            current = float(item.get("information_confidence", 0.0))
            item["information_confidence"] = round(
                max(10.0, current - penalty),
                1,
            )
            warnings.append(
                (
                    f"{count} numerisk konflikt(er) med andra oberoende "
                    f"domäner sänkte informationskonfidensen med "
                    f"{penalty:.1f} poäng."
                )
            )

        item["warning_flags"] = warnings
        item["conflict_count"] = count
        adjusted.append(item)

    return adjusted
