from difflib import SequenceMatcher
import re


STOPWORDS = {
    "den", "det", "en", "ett", "min", "mitt", "mina",
    "the", "a", "an", "my",
}

DESTRUCTIVE_PHRASES = (
    "radera",
    "ta bort",
    "skriv över",
    "skriva över",
    "formatera",
    "delete",
    "remove",
    "overwrite",
    "format",
)

SYSTEM_ACTION_PHRASES = (
    "stäng av",
    "starta om",
    "installera",
    "avinstallera",
    "ändra nätverk",
    "ändra system",
    "shutdown",
    "reboot",
    "install",
    "uninstall",
)

HARDWARE_ACTION_WORDS = (
    "anslut",
    "koppla",
    "aktivera",
    "avaktivera",
    "slå på",
    "slå av",
    "starta",
    "stoppa",
    "driv",
    "connect",
    "disconnect",
    "enable",
    "disable",
)

HARDWARE_TARGET_WORDS = (
    "gpio",
    "motor",
    "relä",
    "relay",
    "solenoid",
    "bluetooth",
    "usb",
    "ström",
    "spänning",
    "power",
    "voltage",
)

FILE_ACTION_WORDS = (
    "skapa fil",
    "skriv fil",
    "ändra fil",
    "spara fil",
    "ändra koden",
    "skriv kod",
    "create file",
    "write file",
    "modify file",
    "change code",
)


def normalize_transcript(text):
    value = (text or "").lower()
    value = re.sub(r"[^a-zåäö0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _tokens(text):
    return {
        token
        for token in normalize_transcript(text).split()
        if token not in STOPWORDS
    }


def transcript_similarity(first, second):
    a = normalize_transcript(first)
    b = normalize_transcript(second)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    sequence = max(
        SequenceMatcher(
            None,
            a,
            b,
        ).ratio(),
        SequenceMatcher(
            None,
            a.replace(" ", ""),
            b.replace(" ", ""),
        ).ratio(),
    )
    a_tokens = _tokens(a)
    b_tokens = _tokens(b)
    union = a_tokens | b_tokens
    jaccard = (
        len(a_tokens & b_tokens) / len(union)
        if union
        else 0.0
    )

    return round(
        0.65 * sequence + 0.35 * jaccard,
        4,
    )


def command_action_signature(text):
    normalized = normalize_transcript(text)

    action_groups = (
        (
            "delete",
            (
                "radera",
                "ta bort",
                "delete",
                "remove",
            ),
        ),
        (
            "overwrite",
            (
                "skriv över",
                "skriva över",
                "overwrite",
            ),
        ),
        (
            "format",
            (
                "formatera",
                "format",
            ),
        ),
        (
            "shutdown",
            (
                "stäng av",
                "shutdown",
            ),
        ),
        (
            "reboot",
            (
                "starta om",
                "reboot",
            ),
        ),
        (
            "install",
            (
                "installera",
                "install",
            ),
        ),
        (
            "uninstall",
            (
                "avinstallera",
                "uninstall",
            ),
        ),
        (
            "file_create",
            (
                "skapa fil",
                "skapa filen",
                "create file",
            ),
        ),
        (
            "file_write",
            (
                "skriv fil",
                "skriv till fil",
                "skriv till filen",
                "ändra fil",
                "ändra filen",
                "spara fil",
                "spara filen",
                "write file",
                "modify file",
            ),
        ),
        (
            "file_read",
            (
                "läs fil",
                "läs filen",
                "read file",
            ),
        ),
    )

    for name, phrases in action_groups:
        if any(
            phrase in normalized
            for phrase in phrases
        ):
            return name

    has_hardware_action = [
        word
        for word in HARDWARE_ACTION_WORDS
        if word in normalized
    ]
    has_hardware_target = [
        word
        for word in HARDWARE_TARGET_WORDS
        if word in normalized
    ]

    if has_hardware_action and has_hardware_target:
        return (
            "hardware:"
            + has_hardware_action[0]
            + ":"
            + has_hardware_target[0]
        )

    return None


def command_risk(text):
    normalized = normalize_transcript(text)

    if any(
        phrase in normalized
        for phrase in DESTRUCTIVE_PHRASES
    ):
        return "high"

    if any(
        phrase in normalized
        for phrase in SYSTEM_ACTION_PHRASES
    ):
        return "high"

    if any(
        phrase in normalized
        for phrase in FILE_ACTION_WORDS
    ):
        return "high"

    has_hardware_action = any(
        word in normalized
        for word in HARDWARE_ACTION_WORDS
    )
    has_hardware_target = any(
        word in normalized
        for word in HARDWARE_TARGET_WORDS
    )

    if has_hardware_action and has_hardware_target:
        return "high"

    return "normal"


def needs_redundant_stt(
    transcript,
    settings,
):
    config = settings.get("voice", {})
    confidence = float(
        transcript.get("confidence", 0.0)
    )
    uncertain_words = int(
        transcript.get("uncertain_words", 0) or 0
    )
    text = transcript.get("text", "")

    if (
        command_risk(text) == "high"
        and config.get(
            "redundant_for_high_risk",
            True,
        )
    ):
        return True

    if confidence < float(
        config.get(
            "primary_confidence_threshold",
            0.80,
        )
    ):
        return True

    if uncertain_words >= int(
        config.get(
            "uncertain_word_limit",
            1,
        )
    ):
        return True

    return False


def choose_transcript_consensus(
    candidates,
    settings,
):
    config = settings.get("voice", {})
    valid = []

    for candidate in candidates or []:
        text = (candidate.get("text") or "").strip()

        if not text:
            continue

        valid.append(
            {
                **candidate,
                "text": text,
                "confidence": float(
                    candidate.get(
                        "confidence",
                        0.0,
                    )
                ),
            }
        )

    if not valid:
        return {
            "status": "clarify",
            "text": None,
            "risk": "normal",
            "agreement_count": 0,
            "reason": "Ingen användbar transkription finns.",
        }

    max_interpretations = max(
        1,
        min(
            int(
                config.get(
                    "max_interpretations",
                    3,
                )
            ),
            3,
        ),
    )
    valid = valid[:max_interpretations]
    risk = (
        "high"
        if any(
            command_risk(item["text"]) == "high"
            for item in valid
        )
        else "normal"
    )

    if len(valid) == 1:
        primary = valid[0]

        if needs_redundant_stt(
            primary,
            settings,
        ):
            return {
                "status": "needs_more",
                "text": primary["text"],
                "risk": risk,
                "agreement_count": 1,
                "confidence": primary["confidence"],
                "reason": (
                    "Kommandot kräver ytterligare STT-tolkning "
                    "innan det kan accepteras."
                ),
            }

        return {
            "status": "accepted",
            "text": primary["text"],
            "risk": risk,
            "agreement_count": 1,
            "confidence": primary["confidence"],
            "reason": "Primär transkription har tillräcklig säkerhet.",
        }

    agreement_threshold = float(
        config.get(
            "agreement_threshold",
            0.72,
        )
    )
    groups = []

    for index, candidate in enumerate(valid):
        members = []

        for other_index, other in enumerate(valid):
            if risk == "high":
                leader_action = command_action_signature(
                    candidate["text"]
                )
                other_action = command_action_signature(
                    other["text"]
                )

                if leader_action != other_action:
                    continue

            similarity = transcript_similarity(
                candidate["text"],
                other["text"],
            )

            if similarity >= agreement_threshold:
                members.append(other_index)

        groups.append(
            {
                "leader_index": index,
                "members": members,
            }
        )

    best = max(
        groups,
        key=lambda group: (
            len(group["members"]),
            valid[group["leader_index"]]["confidence"],
        ),
    )
    agreement_count = len(best["members"])

    if agreement_count < 2:
        return {
            "status": "clarify",
            "text": None,
            "risk": risk,
            "agreement_count": agreement_count,
            "reason": (
                "STT-tolkningarna är inte tillräckligt överens."
            ),
        }

    members = [
        valid[index]
        for index in best["members"]
    ]
    chosen = max(
        members,
        key=lambda item: item["confidence"],
    )
    average_confidence = sum(
        item["confidence"]
        for item in members
    ) / len(members)

    required_confidence = float(
        config.get(
            (
                "high_risk_confidence_threshold"
                if risk == "high"
                else "consensus_confidence_threshold"
            ),
            0.90 if risk == "high" else 0.75,
        )
    )

    if average_confidence < required_confidence:
        return {
            "status": "clarify",
            "text": None,
            "risk": risk,
            "agreement_count": agreement_count,
            "confidence": round(
                average_confidence,
                4,
            ),
            "reason": (
                "STT-tolkningarna liknar varandra men den "
                "sammanlagda säkerheten är för låg."
            ),
        }

    return {
        "status": "accepted",
        "text": chosen["text"],
        "risk": risk,
        "agreement_count": agreement_count,
        "confidence": round(
            average_confidence,
            4,
        ),
        "reason": (
            "Flera STT-tolkningar når tillräcklig konsensus."
        ),
    }
