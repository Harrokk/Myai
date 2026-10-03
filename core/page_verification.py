import re
from urllib.parse import urlparse


METHOD_TERMS = (
    "method",
    "methodology",
    "methods",
    "metod",
    "metodik",
    "material och metod",
    "study design",
)

REFERENCE_TERMS = (
    "references",
    "referenser",
    "sources",
    "källor",
    "bibliography",
    "doi.org/",
)

DATA_TERMS = (
    "data",
    "dataset",
    "sample",
    "urval",
    "result",
    "results",
    "resultat",
    "measurement",
    "measurements",
    "mätning",
    "mätningar",
)

LIMITATION_TERMS = (
    "limitations",
    "limitation",
    "begränsningar",
    "begränsning",
    "uncertainty",
    "osäkerhet",
)


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(float(value), high))


def _first_metadata(metadata, keys):
    metadata = metadata or {}

    for key in keys:
        value = metadata.get(key)

        if value:
            return str(value).strip()

    return ""


def _contains_any(text, terms):
    lowered = (text or "").lower()
    return any(term in lowered for term in terms)


def _query_overlap(query, text):
    query_tokens = set(
        re.findall(
            r"[a-zåäö0-9][a-zåäö0-9_-]{2,}",
            (query or "").lower(),
        )
    )

    if not query_tokens:
        return 0.0

    page_tokens = set(
        re.findall(
            r"[a-zåäö0-9][a-zåäö0-9_-]{2,}",
            (text or "").lower(),
        )
    )

    return len(query_tokens & page_tokens) / len(query_tokens)


def verify_page_content(page, query=""):
    text = page.get("text", "") or ""
    metadata = page.get("metadata", {}) or {}
    title = (page.get("title") or "").strip()
    canonical = (page.get("canonical_url") or "").strip()
    external_links = page.get("external_links") or []

    author = _first_metadata(
        metadata,
        (
            "author",
            "article:author",
            "byl",
        ),
    )
    published_date = _first_metadata(
        metadata,
        (
            "article:published_time",
            "datepublished",
            "date",
            "dc.date",
        ),
    )
    description = _first_metadata(
        metadata,
        (
            "description",
            "og:description",
        ),
    )
    site_name = _first_metadata(
        metadata,
        (
            "og:site_name",
            "application-name",
        ),
    )

    method_signal = _contains_any(text, METHOD_TERMS)
    references_signal = _contains_any(text, REFERENCE_TERMS)
    data_signal = _contains_any(text, DATA_TERMS)
    limitations_signal = _contains_any(text, LIMITATION_TERMS)
    doi_signal = bool(
        re.search(
            r"\b10\.\d{4,9}/[-._;()/:a-z0-9]+",
            text,
            flags=re.IGNORECASE,
        )
    )
    query_overlap = _query_overlap(
        query,
        f"{title} {description} {text[:20_000]}",
    )

    transparency = 20.0
    transparency_reasons = []

    if title:
        transparency += 10
        transparency_reasons.append("Sidan har en tydlig titel.")

    if author:
        transparency += 15
        transparency_reasons.append("Författaruppgift finns i sidmetadata.")
    else:
        transparency_reasons.append("Författaruppgift saknas i sidmetadata.")

    if published_date:
        transparency += 10
        transparency_reasons.append("Publiceringsdatum finns i sidmetadata.")
    else:
        transparency_reasons.append("Publiceringsdatum saknas i sidmetadata.")

    if description:
        transparency += 5
        transparency_reasons.append("Beskrivande metadata finns.")

    if canonical:
        transparency += 5
        transparency_reasons.append("Canonical-URL finns.")

    if site_name:
        transparency += 5
        transparency_reasons.append("Utgivande webbplats anges i metadata.")

    if len(text) >= 1_500:
        transparency += 10
        transparency_reasons.append("Sidan innehåller substantiell text.")

    if limitations_signal:
        transparency += 5
        transparency_reasons.append("Begränsningar/osäkerhet diskuteras.")

    transparency = round(_clamp(transparency, 10, 90), 1)

    evidence = 15.0
    evidence_reasons = []

    if method_signal:
        evidence += 20
        evidence_reasons.append("Metod/metodik nämns i sidtexten.")

    if data_signal:
        evidence += 15
        evidence_reasons.append("Data, mätning eller resultat nämns.")

    if references_signal:
        evidence += 15
        evidence_reasons.append("Referens- eller källsektion indikeras.")

    if doi_signal:
        evidence += 10
        evidence_reasons.append("DOI-liknande referens hittades.")

    if external_links:
        evidence += min(len(set(external_links)), 5) * 3
        evidence_reasons.append(
            f"{len(set(external_links))} externa länk(ar) hittades."
        )

    if limitations_signal:
        evidence += 5
        evidence_reasons.append("Begränsningar/osäkerhet diskuteras.")

    if query:
        evidence += query_overlap * 10
        evidence_reasons.append(
            f"Frågeöverlapp i sidtexten: {query_overlap * 100:.1f}%."
        )

    if not evidence_reasons:
        evidence_reasons.append(
            "Inga tydliga metod-, data- eller referenssignaler hittades."
        )

    evidence = round(_clamp(evidence, 10, 85), 1)

    final_url = page.get("final_url") or page.get("requested_url") or ""
    hostname = (urlparse(final_url).hostname or "").lower()

    return {
        "url": final_url,
        "hostname": hostname,
        "title": title,
        "author": author or None,
        "published_date": published_date or None,
        "site_name": site_name or None,
        "canonical_url": canonical or None,
        "text_length": len(text),
        "external_link_count": len(set(external_links)),
        "signals": {
            "method": method_signal,
            "data_or_results": data_signal,
            "references": references_signal,
            "doi": doi_signal,
            "limitations": limitations_signal,
        },
        "query_overlap_percent": round(query_overlap * 100, 1),
        "transparency_score": transparency,
        "transparency_reasons": transparency_reasons,
        "evidence_signal_score": evidence,
        "evidence_reasons": evidence_reasons,
        "verification_scope": "fetched_page_signals",
        "assessment_note": (
            "Poängen mäter transparens och evidenssignaler på sidan. "
            "De är inte en sannolikhet för att sidans påståenden är sanna."
        ),
    }
