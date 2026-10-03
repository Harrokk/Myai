import re
from urllib.parse import urlparse


NUMBER_UNIT_PATTERN = re.compile(
    r"(?P<value>-?\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>%|percent|procent|v|volt|a|ampere|w|watt|"
    r"°c|celsius|kg|g|mg|km|m|cm|mm|sek|kr|usd|eur)",
    flags=re.IGNORECASE,
)

STOPWORDS = {
    "och", "eller", "att", "det", "den", "som", "för", "med", "från",
    "till", "är", "var", "the", "and", "or", "for", "with", "from",
}


def _host(url):
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def _tokens(text):
    return {
        token
        for token in re.findall(
            r"[a-zåäö0-9][a-zåäö0-9_-]{2,}",
            (text or "").lower(),
        )
        if token not in STOPWORDS
    }


def _numeric_claims(text):
    claims = []

    for match in NUMBER_UNIT_PATTERN.finditer(text or ""):
        raw_value = match.group("value").replace(",", ".")

        try:
            value = float(raw_value)
        except ValueError:
            continue

        unit = match.group("unit").lower()
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
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


def detect_numeric_conflicts(candidates, relative_tolerance=0.05):
    conflicts = []

    for index, first in enumerate(candidates):
        first_host = _host(first.get("url"))
        first_text = (
            (first.get("title") or "")
            + " "
            + (first.get("snippet") or "")
        )
        first_claims = _numeric_claims(first_text)

        for second in candidates[index + 1:]:
            second_host = _host(second.get("url"))

            if not first_host or not second_host or first_host == second_host:
                continue

            second_text = (
                (second.get("title") or "")
                + " "
                + (second.get("snippet") or "")
            )
            second_claims = _numeric_claims(second_text)

            for first_claim in first_claims:
                for second_claim in second_claims:
                    if first_claim["unit"] != second_claim["unit"]:
                        continue

                    similarity = _context_similarity(
                        first_claim,
                        second_claim,
                    )

                    if similarity < 0.25:
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
                            "context_similarity": round(
                                similarity,
                                3,
                            ),
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
    weights,
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

        if count:
            info = dict(item["information_confidence"])
            current = float(info["score"])
            penalty = min(
                float(penalty_per_conflict) * count,
                30.0,
            )
            info["score"] = round(
                max(10.0, current - penalty),
                1,
            )
            info["reasons"] = list(
                info.get("reasons", [])
            ) + [
                (
                    f"{count} numerisk konflikt(er) med andra oberoende "
                    f"domäner sänkte konfidensen med {penalty:.1f} poäng."
                )
            ]
            item["information_confidence"] = info
            item["conflict_count"] = count

            item["combined_score"] = round(
                float(item["relevance"]) * weights["relevance"]
                + float(item["source_reliability"]["score"])
                * weights["source_reliability"]
                + float(info["score"])
                * weights["information_confidence"],
                1,
            )
        else:
            item["conflict_count"] = 0

        adjusted.append(item)

    adjusted.sort(
        key=lambda item: (
            item["combined_score"],
            item["source_reliability"]["score"],
            item["information_confidence"]["score"],
        ),
        reverse=True,
    )
    return adjusted
