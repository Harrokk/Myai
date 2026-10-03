import re

from core.config import load_settings
from core.page_verification import verify_page_content
from core.source_conflicts import (
    apply_conflict_penalties,
    detect_numeric_conflicts,
)
from modules.internet.evaluation import select_top_candidates
from modules.internet.fetch import fetch_public_page
from modules.internet.search import extract_search_query, search_web
from modules.internet.verify import scores_from_verification


STOPWORDS = {
    "och", "eller", "att", "det", "den", "som", "för", "med", "från",
    "till", "är", "var", "hur", "vad", "vilka", "the", "and", "or",
    "for", "with", "from", "this", "that", "what", "how",
}


def _tokens(text):
    return {
        token
        for token in re.findall(
            r"[a-zåäö0-9][a-zåäö0-9_-]{2,}",
            (text or "").lower(),
        )
        if token not in STOPWORDS
    }


def metadata_relevance(query, candidate):
    query_tokens = _tokens(query)

    if not query_tokens:
        return 0.0

    title_tokens = _tokens(candidate.get("title", ""))
    snippet_tokens = _tokens(candidate.get("snippet", ""))

    title_match = len(query_tokens & title_tokens) / len(query_tokens)
    snippet_match = len(query_tokens & snippet_tokens) / len(query_tokens)

    return round(
        min(
            100.0,
            100.0 * (0.65 * title_match + 0.35 * snippet_match),
        ),
        1,
    )


def _call_search(search_function, query, settings):
    try:
        return search_function(query, settings=settings)
    except TypeError:
        return search_function(query=query, settings=settings)


def _call_fetch(fetch_function, url, settings):
    try:
        return fetch_function(url, settings=settings)
    except TypeError:
        return fetch_function(url)


def research_top_candidates_data(
    query,
    settings=None,
    search_function=None,
    fetch_function=None,
):
    settings = settings or load_settings()
    research_config = settings.get("research", {})
    candidate_limit = max(
        1,
        min(int(research_config.get("candidate_limit", 5)), 5),
    )

    active_search = search_function or search_web
    active_fetch = fetch_function or fetch_public_page

    search_result = _call_search(
        active_search,
        query,
        settings,
    )

    if not search_result.get("success"):
        return {
            "available": False,
            "reason": search_result.get(
                "error",
                "Internetsökningen kunde inte köras.",
            ),
            "query": query,
            "candidate_count": 0,
            "top_candidates": [],
            "conflicts": [],
        }

    raw_candidates = list(
        search_result.get("results", [])
    )[:candidate_limit]
    validated = []

    for result in raw_candidates:
        url = result.get("url") or ""
        page = _call_fetch(
            active_fetch,
            url,
            settings,
        )

        if not page.get("available"):
            validated.append(
                {
                    "name": result.get("title") or url or "Okänd källa",
                    "title": result.get("title") or "",
                    "url": url,
                    "snippet": result.get("snippet") or "",
                    "relevance": metadata_relevance(query, result),
                    "source_reliability": 20.0,
                    "information_confidence": 10.0,
                    "warning_flags": [
                        "Källsidan kunde inte hämtas och verifieras."
                    ],
                    "disqualify": True,
                    "critical_warning": False,
                    "page_text": "",
                    "verification": None,
                }
            )
            continue

        verification = verify_page_content(
            page,
            query=query,
        )
        scores = scores_from_verification(
            verification,
        )
        relevance = max(
            metadata_relevance(query, result),
            verification["query_overlap_percent"],
        )

        validated.append(
            {
                "name": result.get("title") or url or "Okänd källa",
                "title": result.get("title") or page.get("title") or "",
                "url": page.get("final_url") or url,
                "snippet": result.get("snippet") or "",
                "relevance": round(min(100.0, relevance), 1),
                "source_reliability": scores["source_reliability"],
                "information_confidence": scores[
                    "information_confidence"
                ],
                "warning_flags": [],
                "disqualify": False,
                "critical_warning": False,
                "page_text": page.get("text") or "",
                "verification": verification,
            }
        )

    conflicts = detect_numeric_conflicts(validated)
    adjusted = apply_conflict_penalties(
        validated,
        conflicts,
        penalty_per_conflict=10.0,
    )
    ranking = select_top_candidates(
        adjusted,
        settings=settings,
    )

    return {
        "available": True,
        "query": query,
        "candidate_count": len(raw_candidates),
        "validated_count": len(validated),
        "top_candidates": ranking["top_candidates"],
        "excluded_candidates": ranking["excluded_candidates"],
        "evaluated_candidates": ranking["evaluated_candidates"],
        "conflicts": conflicts,
        "basis_fewer_than_limit": len(raw_candidates) < candidate_limit,
        "candidate_limit": candidate_limit,
        "assessment_note": (
            "Käll- och informationspoängen är interna heuristiker. "
            "Sidor hämtas och granskas var för sig, och tydliga numeriska "
            "motsägelser mellan oberoende domäner sänker konfidensen. "
            "Poängen är inte sannolikheter eller sanningsgarantier."
        ),
    }


def format_research_top_candidates(result):
    if not result.get("available"):
        return "Research kunde inte köras: " + result.get(
            "reason",
            "okänd orsak",
        )

    lines = [
        (
            f"Validerat underlag: {result.get('candidate_count', 0)} "
            "kandidat(er)."
        )
    ]

    if result.get("basis_fewer_than_limit"):
        lines.append(
            "Underlaget innehåller färre kandidater än målet "
            f"{result.get('candidate_limit', 5)}."
        )

    conflicts = result.get("conflicts", [])

    if conflicts:
        lines.append(
            f"Numeriska källkonflikter upptäckta: {len(conflicts)}."
        )
    else:
        lines.append("Inga tydliga numeriska källkonflikter upptäcktes.")

    top = result.get("top_candidates", [])
    lines.append("Toppkandidater efter verifiering:")

    if not top:
        lines.append("- Inga kandidater klarade valideringskraven.")
    else:
        for index, item in enumerate(top, start=1):
            lines.append(
                f"{index}. {item['name']} — "
                f"källa {item['source_reliability']:.1f}%, "
                f"info {item['information_confidence']:.1f}%, "
                f"relevans {item['relevance']:.1f}%"
            )
            if item.get("url"):
                lines.append(f"   {item['url']}")

    lines.append(result["assessment_note"])
    return "\n".join(lines)


def research_top_three(user_input):
    try:
        query = extract_search_query(user_input)

        prefixes = (
            "researcha ",
            "gör research om ",
            "undersök ",
            "jämför källor om ",
            "verifiera information om ",
        )
        lowered = query.lower()

        for prefix in prefixes:
            if lowered.startswith(prefix):
                query = query[len(prefix):].strip()
                break

        if not query:
            return "Research kunde inte köras: sökfrågan är tom."

        return format_research_top_candidates(
            research_top_candidates_data(query)
        )
    except Exception as error:
        return f"Research kunde inte köras: {error}"


TOOLS = {
    "research_top_three": {
        "function": research_top_three,
        "description": (
            "Söker upp till fem webbkällor, hämtar och verifierar sidorna, "
            "sänker informationskonfidensen vid tydliga numeriska konflikter "
            "mellan oberoende domäner och presenterar de starkaste "
            "kandidaterna."
        ),
        "pass_user_input": True,
    }
}
