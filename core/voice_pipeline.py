from difflib import SequenceMatcher
import re


HIGH_RISK_TERMS = (
    "radera",
    "ta bort",
    "delete",
    "remove",
    "skriv över",
    "overwrite",
    "formatera",
    "format disk",
    "stäng av",
    "shutdown",
    "starta om",
    "reboot",
    "installera",
    "uninstall",
    "avinstallera",
    "gpio",
    "motor",
    "relä",
    "relay",
    "bluetooth on",
    "bluetooth off",
    "anslut till",
    "koppla från",
    "ändra system",
    "systeminställning",
    "redigera fil",
    "ändra fil",
    "ändra kod",
    "skriv kod",
    "commit",
    "merge",
    "push",
)

EXPLICIT_HIGH_SAFETY_TERMS = (
    "hög säkerhet",
    "extra kontroll",
    "verifiera kommandot",
    "dubbelkolla kommandot",
)

NORMALIZE_WORDS = {
    "datorn": "dator",
    "datorns": "dator",
    "ramminne": "ram",
    "ram-minne": "ram",
    "används": "använd",
    "använder": "använd",
    "använda": "använd",
    "koppla": "anslut",
    "ansluta": "anslut",
}


def normalize_transcript(text):
    value = (text or "").lower().strip()
    value = re.sub(r"[^a-z0-9åäö\- ]+", " ", value)
    words = []

    for word in value.split():
        words.append(
            NORMALIZE_WORDS.get(word, word)
        )

    return " ".join(words)


def transcript_similarity(first, second):
    left = normalize_transcript(first)
    right = normalize_transcript(second)

    if not left or not right:
        return 0.0

    left_tokens = set(left.split())
    right_tokens = set(right.split())
    union = left_tokens | right_tokens
    jaccard = (
        len(left_tokens & right_tokens) / len(union)
        if union
        else 0.0
    )
    sequence = SequenceMatcher(
        None,
        left,
        right,
    ).ratio()

    return round(max(jaccard, sequence), 3)


def classify_voice_risk(text):
    normalized = normalize_transcript(text)
    reasons = []

    for term in HIGH_RISK_TERMS:
        if normalize_transcript(term) in normalized:
            reasons.append(
                f"riskterm: {term}"
            )

    for term in EXPLICIT_HIGH_SAFETY_TERMS:
        if normalize_transcript(term) in normalized:
            reasons.append(
                f"användaren begär hög säkerhet: {term}"
            )

    return {
        "level": "high" if reasons else "low",
        "reasons": reasons,
    }


def normalize_stt_result(result):
    if isinstance(result, str):
        return {
            "text": result.strip(),
            "confidence": None,
        }

    if not isinstance(result, dict):
        raise ValueError(
            "STT-resultat måste vara text eller ett objekt."
        )

    text = str(
        result.get("text") or ""
    ).strip()
    confidence = result.get("confidence")

    if confidence is not None:
        confidence = float(confidence)
        confidence = max(
            0.0,
            min(confidence, 1.0),
        )

    return {
        "text": text,
        "confidence": confidence,
    }


def choose_consensus(
    transcripts,
    similarity_threshold=0.62,
):
    normalized = [
        normalize_stt_result(item)
        for item in transcripts
        if item is not None
    ]

    normalized = [
        item
        for item in normalized
        if item["text"]
    ]

    if not normalized:
        return {
            "accepted": False,
            "reason": "Ingen användbar transkription.",
            "text": None,
            "support": 0,
            "transcripts": [],
        }

    if len(normalized) == 1:
        return {
            "accepted": True,
            "reason": "Endast en transkription användes.",
            "text": normalized[0]["text"],
            "support": 1,
            "transcripts": normalized,
        }

    support = [1] * len(normalized)

    for left_index in range(len(normalized)):
        for right_index in range(
            left_index + 1,
            len(normalized),
        ):
            similarity = transcript_similarity(
                normalized[left_index]["text"],
                normalized[right_index]["text"],
            )

            if similarity >= similarity_threshold:
                support[left_index] += 1
                support[right_index] += 1

    best_index = max(
        range(len(normalized)),
        key=lambda index: (
            support[index],
            normalized[index]["confidence"]
            if normalized[index]["confidence"] is not None
            else -1,
        ),
    )
    best_support = support[best_index]
    required_support = (
        len(normalized) // 2 + 1
    )

    if best_support < required_support:
        return {
            "accepted": False,
            "reason": (
                "STT-tolkningarna saknar tydlig majoritetskonsensus."
            ),
            "text": None,
            "support": best_support,
            "transcripts": normalized,
        }

    return {
        "accepted": True,
        "reason": (
            f"{best_support} av {len(normalized)} tolkningar "
            "är tillräckligt överens."
        ),
        "text": normalized[best_index]["text"],
        "support": best_support,
        "transcripts": normalized,
    }


class VoicePipeline:
    def __init__(
        self,
        assistant,
        primary_stt,
        backup_stt=None,
        tts=None,
        settings=None,
    ):
        self.assistant = assistant
        self.primary_stt = primary_stt
        self.backup_stt = list(
            backup_stt or []
        )
        self.tts = tts
        self.settings = settings or {}

    @property
    def voice_settings(self):
        return self.settings.get("voice", {})

    def _transcribe(self, provider, audio):
        return normalize_stt_result(
            provider.transcribe(audio)
        )

    def _needs_redundancy(
        self,
        primary,
        risk,
    ):
        config = self.voice_settings

        if not config.get(
            "redundancy_enabled",
            True,
        ):
            return False

        if risk["level"] == "high":
            return True

        confidence = primary.get("confidence")

        if confidence is None:
            return bool(
                config.get(
                    "redundancy_when_confidence_missing",
                    False,
                )
            )

        threshold = float(
            config.get(
                "primary_confidence_threshold",
                0.72,
            )
        )
        return confidence < threshold

    def process_utterance(self, audio):
        config = self.voice_settings
        primary = self._transcribe(
            self.primary_stt,
            audio,
        )

        if not primary["text"]:
            return {
                "status": "clarify",
                "message": (
                    "Jag kunde inte uppfatta något tydligt tal. "
                    "Försök igen."
                ),
                "transcripts": [primary],
            }

        risk = classify_voice_risk(
            primary["text"]
        )
        transcripts = [primary]

        if self._needs_redundancy(
            primary,
            risk,
        ):
            desired = max(
                2,
                int(
                    config.get(
                        "redundant_transcript_count",
                        3,
                    )
                ),
            )

            for provider in self.backup_stt:
                if len(transcripts) >= desired:
                    break

                transcripts.append(
                    self._transcribe(
                        provider,
                        audio,
                    )
                )

            if len(transcripts) < desired:
                return {
                    "status": "clarify",
                    "message": (
                        "Kommandot kräver extra talverifiering, "
                        "men inte tillräckligt många STT-tolkningar finns."
                    ),
                    "risk": risk,
                    "transcripts": transcripts,
                }

            consensus = choose_consensus(
                transcripts,
                similarity_threshold=float(
                    config.get(
                        "consensus_similarity_threshold",
                        0.62,
                    )
                ),
            )

            if not consensus["accepted"]:
                return {
                    "status": "clarify",
                    "message": (
                        "Taligenkänningarna är inte tillräckligt "
                        "överens. Bekräfta eller säg kommandot igen."
                    ),
                    "risk": risk,
                    "consensus": consensus,
                    "transcripts": transcripts,
                }

            transcript = consensus["text"]
        else:
            consensus = {
                "accepted": True,
                "text": primary["text"],
                "support": 1,
                "transcripts": transcripts,
                "reason": "Primär STT var tillräcklig.",
            }
            transcript = primary["text"]

        final_risk = classify_voice_risk(
            transcript
        )
        response = self.assistant.respond(
            transcript
        )
        answer = response.get(
            "answer",
            "",
        )

        if (
            self.tts is not None
            and config.get("tts_enabled", False)
            and answer
        ):
            self.tts.speak(answer)

        return {
            "status": "completed",
            "transcript": transcript,
            "risk": final_risk,
            "consensus": consensus,
            "assistant": response,
        }

    def interrupt(self):
        if self.tts is None:
            return False

        stop = getattr(
            self.tts,
            "stop",
            None,
        )

        if not callable(stop):
            return False

        stop()
        return True
