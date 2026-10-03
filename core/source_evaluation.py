import ipaddress
import re
from copy import deepcopy
from urllib.parse import urlparse


STOPWORDS = {
    "och", "eller", "att", "det", "den", "detta", "som", "för", "med",
    "från", "till", "är", "var", "hur", "vad", "vilka", "the", "and",
    "or", "for", "with", "from", "this", "that", "are", "what", "how",
}

SHORTENER_HOSTS = {
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "goo.gl",
    "ow.ly",
}


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(float(value), high))


def _hostname(url):
    try:
        return (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return ""


def _is_ip_host(hostname):
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def _tokens(text):
    words = re.findall(
        r"[a-zåäö0-9][a-zåäö0-9_-]{2,}",
        (text or "").lower(),
    )
    return {
        word
        for word in words
        if word not in STOPWORDS
    }


def relevance_score(query, candidate):
    query_tokens = _tokens(query)

    if not query_tokens:
        return 0.0

    title_tokens = _tokens(candidate.get("title", ""))
    snippet_tokens = _tokens(candidate.get("snippet", ""))

    title_match = len(query_tokens & title_tokens) / len(query_tokens)
    snippet_match = len(query_tokens & snippet_tokens) / len(query_tokens)

    score = 100.0 * (
        0.65 * title_match
        + 0.35 * snippet_match
    )
    return round(_clamp(score), 1)


def source_reliability(candidate):
    score = 35.0
    reasons = [
        "Bedömningen är preliminär och bygger endast på sökmetadata."
    ]

    url = candidate.get("url", "")
    parsed = urlparse(url)
    host = _hostname(url)

    if parsed.scheme == "https":
        score += 10
        reasons.append("HTTPS används.")
    else:
        score -= 5
        reasons.append("HTTPS kunde inte verifieras.")

    if host:
        if _is_ip_host(host):
            score -= 15
            reasons.append("URL använder rå IP-adress.")
        else:
            score += 10
            reasons.append("Tydligt domännamn finns.")

        if host.startswith("xn--") or ".xn--" in host:
            score -= 10
            reasons.append("Punycode-domän kräver extra kontroll.")

        if host in SHORTENER_HOSTS:
            score -= 15
            reasons.append("Kortlänk döljer slutlig domän.")
    else:
        score -= 15
        reasons.append("Domännamn saknas.")

    if (candidate.get("title") or "").strip():
        score += 5

    snippet = (candidate.get("snippet") or "").strip()

    if len(snippet) >= 80:
        score += 5
        reasons.append("Sökresultatet har ett informativt utdrag.")
    elif not snippet:
        score -= 5
        reasons.append("Utdrag saknas.")

    if candidate.get("published_date"):
        score += 5
        reasons.append("Publiceringsinformation finns.")

    engines = candidate.get("engines") or []

    if len(set(engines)) >= 2:
        score += 5
        reasons.append("Resultatet hittades av flera sökmotorer.")

    score = round(_clamp(score, 10, 80), 1)

    return {
        "score": score,
        "reasons": reasons,
        "scope": "preliminary_metadata",
    }


def _corroborating_domains(candidate, candidates):
    host = _hostname(candidate.get("url", ""))
    tokens = _tokens(
        (candidate.get("title") or "")
        + " "
        + (candidate.get("snippet") or "")
    )
    corroborating = set()

    if len(tokens) < 3:
        return corroborating

    for other in candidates:
        if other is candidate:
            continue

        other_host = _hostname(other.get("url", ""))

        if not other_host or other_host == host:
            continue

        other_tokens = _tokens(
            (other.get("title") or "")
            + " "
            + (other.get("snippet") or "")
        )

        if len(other_tokens) < 3:
            continue

        shared = tokens & other_tokens
        union = tokens | other_tokens

        if len(shared) < 3 or not union:
            continue

        similarity = len(shared) / len(union)

        if similarity >= 0.20:
            corroborating.add(other_host)

    return corroborating


def information_confidence(candidate, candidates):
    score = 30.0
    reasons = [
        "Bedömningen gäller endast information som syns i sökresultatets metadata/utdrag."
    ]

    snippet = (candidate.get("snippet") or "").strip()

    if len(snippet) >= 120:
        score += 10
        reasons.append("Utdraget innehåller relativt mycket kontext.")
    elif not snippet:
        score -= 10
        reasons.append("Utdrag saknas.")

    if candidate.get("published_date"):
        score += 5
        reasons.append("Publiceringsinformation finns.")

    corroborating = _corroborating_domains(
        candidate,
        candidates,
    )

    if corroborating:
        bonus = min(len(corroborating), 3) * 10
        score += bonus
        reasons.append(
            f"Liknande uppgifter syns på {len(corroborating)} annan/andra domän(er)."
        )
    else:
        reasons.append(
            "Ingen oberoende domänbekräftelse kunde utläsas ur sökutdragen."
        )

    score = round(_clamp(score, 10, 75), 1)

    return {
        "score": score,
        "reasons": reasons,
        "corroborating_domains": sorted(corroborating),
        "scope": "preliminary_snippet",
    }


def _normalized_weights(weights=None):
    weights = weights or {
        "relevance": 0.40,
        "source_reliability": 0.35,
        "information_confidence": 0.25,
    }

    values = {
        key: max(0.0, float(weights.get(key, 0.0)))
        for key in (
            "relevance",
            "source_reliability",
            "information_confidence",
        )
    }
    total = sum(values.values())

    if total <= 0:
        raise ValueError("Vikterna för källbedömningen får inte summera till 0.")

    return {
        key: value / total
        for key, value in values.items()
    }


def evaluate_candidates(query, candidates, weights=None):
    weights = _normalized_weights(weights)
    evaluated = []

    for candidate in candidates:
        reliability = source_reliability(candidate)
        confidence = information_confidence(
            candidate,
            candidates,
        )
        relevance = relevance_score(query, candidate)

        combined = (
            relevance * weights["relevance"]
            + reliability["score"] * weights["source_reliability"]
            + confidence["score"] * weights["information_confidence"]
        )

        evaluated.append(
            {
                **candidate,
                "relevance": relevance,
                "source_reliability": reliability,
                "information_confidence": confidence,
                "combined_score": round(combined, 1),
            }
        )

    evaluated.sort(
        key=lambda item: (
            item["combined_score"],
            item["source_reliability"]["score"],
            item["information_confidence"]["score"],
        ),
        reverse=True,
    )
    return evaluated


def apply_deep_verification(
    candidate,
    verification,
    weights=None,
    deep_blend=0.40,
):
    """Blanda preliminära sökpoäng med verifierade sid-signaler."""
    result = deepcopy(candidate)
    weights = _normalized_weights(weights)
    blend = _clamp(float(deep_blend), 0.0, 1.0)

    preliminary_source = float(
        result["source_reliability"]["score"]
    )
    preliminary_information = float(
        result["information_confidence"]["score"]
    )

    transparency = float(
        verification.get("transparency_score", 0.0)
    )
    evidence = float(
        verification.get("evidence_signal_score", 0.0)
    )

    adjusted_source = round(
        _clamp(
            preliminary_source * (1.0 - blend)
            + transparency * blend,
            10,
            90,
        ),
        1,
    )
    adjusted_information = round(
        _clamp(
            preliminary_information * (1.0 - blend)
            + evidence * blend,
            10,
            85,
        ),
        1,
    )

    source_info = deepcopy(result["source_reliability"])
    source_info["preliminary_score"] = preliminary_source
    source_info["score"] = adjusted_source
    source_info["scope"] = "metadata_plus_page_signals"
    source_info["reasons"] = list(
        source_info.get("reasons", [])
    ) + [
        (
            "Djupverifierad sidtransparens blandades in "
            f"med vikt {blend:.2f}."
        )
    ]

    information_info = deepcopy(
        result["information_confidence"]
    )
    information_info["preliminary_score"] = preliminary_information
    information_info["score"] = adjusted_information
    information_info["scope"] = "snippet_plus_page_signals"
    information_info["reasons"] = list(
        information_info.get("reasons", [])
    ) + [
        (
            "Djupverifierade evidenssignaler blandades in "
            f"med vikt {blend:.2f}."
        )
    ]

    combined = (
        float(result["relevance"]) * weights["relevance"]
        + adjusted_source * weights["source_reliability"]
        + adjusted_information * weights["information_confidence"]
    )

    result["source_reliability"] = source_info
    result["information_confidence"] = information_info
    result["combined_score"] = round(combined, 1)
    result["deep_verification"] = verification
    result["deep_verification_status"] = "verified"

    return result
