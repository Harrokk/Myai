import re
from difflib import SequenceMatcher


SENSITIVE_PATTERNS = (
    r"\blösenord\b",
    r"\bpassword\b",
    r"\bpin[- ]?kod\b",
    r"\bpin code\b",
    r"\bapi[- ]?nyckel\b",
    r"\bapi key\b",
    r"\baccess token\b",
    r"\brefresh token\b",
    r"\bhemlig nyckel\b",
    r"\bsecret key\b",
    r"\bprivat nyckel\b",
    r"\bprivate key\b",
    r"\bkortnummer\b",
    r"\bcard number\b",
    r"\bpersonnummer\b",
)

EXPLICIT_MEMORY_PHRASES = (
    "kom ihåg",
    "lägg på minnet",
    "spara detta",
    "spara att",
    "remember this",
    "remember that",
)

PREFERENCE_PHRASES = (
    "jag föredrar",
    "jag föredrar att",
    "jag vill alltid",
    "jag vill att du alltid",
    "min standard är",
    "jag brukar vilja",
    "i prefer",
    "i always want",
)

RULE_PHRASES = (
    "från och med nu",
    "hädanefter",
    "det ska alltid",
    "ska alltid",
    "använd alltid",
    "ändra standard",
    "from now on",
    "always use",
)

PROJECT_PHRASES = (
    "projektet ska",
    "planen är",
    "nästa steg är",
    "nästa gång ska",
    "vi ska använda",
    "ska byggas",
    "project should",
    "next step is",
)

TRANSIENT_PHRASES = (
    "just nu",
    "idag",
    "ikväll",
    "i kväll",
    "den här gången",
    "tillfälligt",
    "för tillfället",
    "imorgon",
    "today",
    "right now",
    "this time",
    "temporarily",
    "tomorrow",
)


def normalize_memory_text(text):
    value = (text or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def contains_sensitive_memory_data(text):
    normalized = normalize_memory_text(text)

    return any(
        re.search(pattern, normalized)
        for pattern in SENSITIVE_PATTERNS
    )


def _strip_explicit_prefix(text):
    value = (text or "").strip()
    lowered = value.lower()

    prefixes = (
        "kom ihåg att ",
        "kom ihåg ",
        "lägg på minnet att ",
        "lägg på minnet ",
        "spara detta: ",
        "spara att ",
        "remember that ",
        "remember this: ",
    )

    for prefix in prefixes:
        if lowered.startswith(prefix):
            cleaned = value[len(prefix):].strip()
            return cleaned or value

    return value


def _similarity(first, second):
    a = normalize_memory_text(first)
    b = normalize_memory_text(second)

    if not a or not b:
        return 0.0

    return SequenceMatcher(
        None,
        a,
        b,
    ).ratio()


def _recurrence_count(text, prior_messages):
    return sum(
        _similarity(text, prior) >= 0.88
        for prior in (prior_messages or [])
    )


def assess_memory_candidate(
    text,
    settings=None,
    prior_messages=None,
):
    config = (settings or {}).get("memory", {})
    normalized = normalize_memory_text(text)
    reasons = []

    if not normalized:
        return {
            "action": "ignore",
            "score": 0,
            "category": "other",
            "content": "",
            "sensitive": False,
            "reasons": ["Tom text."],
        }

    if contains_sensitive_memory_data(normalized):
        return {
            "action": "ignore",
            "score": 0,
            "category": "sensitive",
            "content": "",
            "sensitive": True,
            "reasons": [
                "Automatisk lagring blockerades eftersom texten innehåller en känslig hemlighets-/identifieringssignal."
            ],
        }

    score = 10
    category = "other"

    explicit = any(
        phrase in normalized
        for phrase in EXPLICIT_MEMORY_PHRASES
    )

    if explicit:
        score += 70
        category = "explicit"
        reasons.append(
            "Användaren uttrycker explicit att informationen ska kommas ihåg."
        )

    if any(
        phrase in normalized
        for phrase in PREFERENCE_PHRASES
    ):
        score += 45
        category = "preference"
        reasons.append(
            "Texten ser ut som en bestående användarpreferens."
        )

    if any(
        phrase in normalized
        for phrase in RULE_PHRASES
    ):
        score += 70
        category = "rule"
        reasons.append(
            "Texten ser ut som en återanvändbar regel eller standardändring."
        )

    if any(
        phrase in normalized
        for phrase in PROJECT_PHRASES
    ):
        score += 45

        if category == "other":
            category = "project"

        reasons.append(
            "Texten ser ut som ett bestående projektbeslut eller nästa steg."
        )

    recurrence = _recurrence_count(
        text,
        prior_messages,
    )

    if recurrence:
        bonus = min(recurrence, 2) * 15
        score += bonus
        reasons.append(
            f"Liknande information har förekommit {recurrence} gång(er) tidigare i korttidskontexten."
        )

    if any(
        phrase in normalized
        for phrase in TRANSIENT_PHRASES
    ):
        score -= 35
        reasons.append(
            "Texten innehåller en tydlig tillfällig tidsmarkör."
        )

    if normalized.endswith("?") and not explicit:
        score -= 20
        reasons.append(
            "En vanlig fråga är normalt inte långtidsminne."
        )

    if len(normalized) < 18 and not explicit:
        score -= 15
        reasons.append(
            "Mycket kort text har lågt automatiskt minnesvärde."
        )

    score = max(0, min(int(round(score)), 100))
    auto_threshold = int(
        config.get(
            "auto_save_threshold",
            80,
        )
    )
    review_threshold = int(
        config.get(
            "review_threshold",
            55,
        )
    )

    if score >= auto_threshold:
        action = "save"
    elif score >= review_threshold:
        action = "review"
    else:
        action = "ignore"

    if not reasons:
        reasons.append(
            "Ingen stark signal för bestående långtidsminne hittades."
        )

    return {
        "action": action,
        "score": score,
        "category": category,
        "content": _strip_explicit_prefix(text),
        "sensitive": False,
        "recurrence_count": recurrence,
        "reasons": reasons,
    }
