from difflib import SequenceMatcher

from core.voice_streaming import StreamingTTSCoordinator
import re
import time


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

VOICE_CONFIRM_PHRASES = {
    "bekräfta",
    "bekräfta kommandot",
    "kör kommandot",
    "confirm",
    "confirm command",
    "yes confirm",
}

VOICE_CANCEL_PHRASES = {
    "avbryt",
    "avbryt kommandot",
    "stoppa kommandot",
    "cancel",
    "cancel command",
}


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


def tts_echo_similarity(
    transcript,
    spoken_text,
    min_words=3,
):
    heard = normalize_transcript(transcript)
    spoken = normalize_transcript(spoken_text)

    if not heard or not spoken:
        return 0.0

    heard_words = heard.split()

    if len(heard_words) < max(1, int(min_words)):
        return 0.0

    heard_tokens = set(heard_words)
    spoken_tokens = set(spoken.split())
    containment = (
        len(heard_tokens & spoken_tokens)
        / len(heard_tokens)
        if heard_tokens
        else 0.0
    )

    return round(
        max(
            transcript_similarity(
                heard,
                spoken,
            ),
            containment,
        ),
        3,
    )


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


def classify_tool_plan_risk(plan, tools):
    reasons = []
    tool_names = []

    if not isinstance(plan, dict) or not isinstance(tools, dict):
        return {
            "level": "low",
            "reasons": reasons,
            "tool_names": tool_names,
        }

    for step in plan.get("steps", []):
        if not isinstance(step, dict):
            continue

        tool_name = step.get("tool")

        if not tool_name or tool_name in tool_names:
            continue

        tool_names.append(tool_name)
        metadata = tools.get(tool_name, {})
        safety = (
            metadata.get("safety", {})
            if isinstance(metadata, dict)
            else {}
        )
        effect = str(
            safety.get("effect", "read_only")
        ).strip().lower()
        requires_confirmation = bool(
            safety.get(
                "voice_confirmation_required",
                False,
            )
        )

        if (
            requires_confirmation
            or effect in {
                "write",
                "mutate",
                "destructive",
            }
        ):
            reasons.append(
                f"verktyg kräver röstbekräftelse: {tool_name}"
            )

    return {
        "level": "high" if reasons else "low",
        "reasons": reasons,
        "tool_names": tool_names,
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
        semantic_resolver=None,
        clock=None,
        before_assistant=None,
    ):
        self.assistant = assistant
        self.primary_stt = primary_stt
        self.backup_stt = list(
            backup_stt or []
        )
        self.tts = tts
        self.settings = settings or {}
        self.semantic_resolver = semantic_resolver
        self.clock = clock or time.monotonic
        self.last_tts_text = ""
        self.last_tts_started_at = None
        self.pending_confirmation = None
        self.streaming_tts = None
        self.before_assistant = before_assistant

    @property
    def voice_settings(self):
        return self.settings.get("voice", {})

    def _classify_risk(self, text):
        phrase_risk = classify_voice_risk(text)
        preview = getattr(
            self.assistant,
            "preview_tool_plan",
            None,
        )
        tools = getattr(
            self.assistant,
            "tools",
            None,
        )

        if not callable(preview) or not isinstance(tools, dict):
            return phrase_risk

        try:
            plan = preview(text)
        except Exception as error:
            reasons = list(
                phrase_risk.get(
                    "reasons",
                    [],
                )
            )
            reasons.append(
                "verktygsplanen kunde inte säkerhetsbedömas"
            )
            return {
                "level": "high",
                "reasons": reasons,
                "tool_names": [],
                "tool_plan_error": type(error).__name__,
            }

        tool_risk = classify_tool_plan_risk(
            plan,
            tools,
        )
        reasons = list(
            dict.fromkeys(
                list(
                    phrase_risk.get(
                        "reasons",
                        [],
                    )
                )
                + list(
                    tool_risk.get(
                        "reasons",
                        [],
                    )
                )
            )
        )

        return {
            "level": (
                "high"
                if (
                    phrase_risk.get("level") == "high"
                    or tool_risk.get("level") == "high"
                )
                else "low"
            ),
            "reasons": reasons,
            "tool_names": tool_risk.get(
                "tool_names",
                [],
            ),
        }

    def _transcribe(self, provider, audio):
        return normalize_stt_result(
            provider.transcribe(audio)
        )

    def _probable_tts_echo(
        self,
        transcript,
        risk,
    ):
        config = self.voice_settings

        if not config.get(
            "echo_guard_enabled",
            True,
        ):
            return None

        if (
            risk.get("level") == "high"
            and not config.get(
                "echo_guard_for_high_risk",
                False,
            )
        ):
            return None

        if (
            not self.last_tts_text
            or self.last_tts_started_at is None
        ):
            return None

        window = max(
            0.0,
            float(
                config.get(
                    "echo_guard_window_seconds",
                    5.0,
                )
            ),
        )
        age = (
            self.clock()
            - self.last_tts_started_at
        )

        if age < 0 or age > window:
            return None

        similarity = tts_echo_similarity(
            transcript,
            self.last_tts_text,
            min_words=config.get(
                "echo_guard_min_words",
                3,
            ),
        )
        threshold = float(
            config.get(
                "echo_guard_similarity_threshold",
                0.78,
            )
        )

        if similarity < threshold:
            return None

        return {
            "status": "ignored_echo",
            "message": (
                "Ignorerade sannolikt själveko från den senaste TTS-uppläsningen."
            ),
            "transcript": transcript,
            "echo_similarity": similarity,
            "echo_age_seconds": round(
                age,
                3,
            ),
        }

    def _stop_streaming_tts(self):
        coordinator = self.streaming_tts

        if coordinator is None:
            return False

        self.streaming_tts = None
        return coordinator.stop()

    def _speak_control_message(self, text):
        config = self.voice_settings

        if (
            self.tts is None
            or not config.get("tts_enabled", False)
            or not text
        ):
            return False

        self._stop_streaming_tts()
        self.last_tts_text = text
        self.last_tts_started_at = self.clock()
        self.tts.speak(text)
        return True

    def _respond_and_speak(self, transcript):
        if self.before_assistant is not None:
            self.before_assistant()

        config = self.voice_settings
        tts_enabled = bool(
            self.tts is not None
            and config.get("tts_enabled", False)
        )
        stream_enabled = bool(
            tts_enabled
            and config.get(
                "llm_streaming_enabled",
                False,
            )
            and callable(
                getattr(
                    self.assistant,
                    "respond_stream",
                    None,
                )
            )
        )

        if stream_enabled:
            self._stop_streaming_tts()
            coordinator = StreamingTTSCoordinator(
                self.tts,
                clock=self.clock,
                min_chars=config.get(
                    "stream_tts_min_chars",
                    24,
                ),
                max_chars=config.get(
                    "stream_tts_max_chars",
                    220,
                ),
                stop_timeout_seconds=config.get(
                    "stream_tts_stop_timeout_seconds",
                    2.0,
                ),
            )
            self.streaming_tts = coordinator

            response = self.assistant.respond_stream(
                transcript,
                on_chunk=coordinator.feed,
            )
            coordinator.finish()
            answer = response.get(
                "answer",
                "",
            )

            if answer:
                self.last_tts_text = answer
                self.last_tts_started_at = (
                    coordinator.started_at
                    if coordinator.started_at is not None
                    else self.clock()
                )

            return response

        response = self.assistant.respond(
            transcript
        )
        answer = response.get(
            "answer",
            "",
        )

        if tts_enabled and answer:
            self.last_tts_text = answer
            self.last_tts_started_at = self.clock()
            self.tts.speak(answer)

        return response

    def _confirmation_message(self, transcript):
        return (
            f"Högriskkommando uppfattat: {transcript}. "
            'Säg "bekräfta" för att köra eller "avbryt".'
        )

    def _handle_pending_confirmation(
        self,
        primary,
        audio,
    ):
        pending = self.pending_confirmation

        if pending is None:
            return None

        config = self.voice_settings
        age = self.clock() - pending["created_at"]
        window = max(
            1.0,
            float(
                config.get(
                    "high_risk_confirmation_window_seconds",
                    15.0,
                )
            ),
        )

        if age < 0 or age > window:
            self.pending_confirmation = None
            message = (
                "Bekräftelsetiden gick ut. "
                "Säg högriskkommandot igen om det fortfarande ska köras."
            )
            self._speak_control_message(message)
            return {
                "status": "confirmation_expired",
                "message": message,
                "transcript": primary["text"],
                "pending_transcript": pending["transcript"],
            }

        normalized = normalize_transcript(
            primary["text"]
        )
        confirm_phrases = {
            normalize_transcript(value)
            for value in VOICE_CONFIRM_PHRASES
        }
        cancel_phrases = {
            normalize_transcript(value)
            for value in VOICE_CANCEL_PHRASES
        }

        if normalized in cancel_phrases:
            self.pending_confirmation = None
            message = "Kommandot avbröts."
            self._speak_control_message(message)
            return {
                "status": "confirmation_cancelled",
                "message": message,
                "transcript": primary["text"],
                "pending_transcript": pending["transcript"],
            }

        if normalized in confirm_phrases:
            confidence = primary.get("confidence")
            threshold = float(
                config.get(
                    "high_risk_confirmation_min_confidence",
                    0.80,
                )
            )
            confirmation_transcripts = [
                primary
            ]
            confirmed = (
                confidence is not None
                and confidence >= threshold
            )

            if not confirmed:
                desired = max(
                    2,
                    int(
                        config.get(
                            "high_risk_confirmation_transcript_count",
                            3,
                        )
                    ),
                )

                for provider in self.backup_stt:
                    if len(
                        confirmation_transcripts
                    ) >= desired:
                        break

                    confirmation_transcripts.append(
                        self._transcribe(
                            provider,
                            audio,
                        )
                    )

                normalized_confirmations = [
                    normalize_transcript(
                        item["text"]
                    )
                    for item in confirmation_transcripts
                ]
                support = sum(
                    1
                    for value in normalized_confirmations
                    if value in confirm_phrases
                )
                majority = (
                    len(
                        confirmation_transcripts
                    ) // 2 + 1
                )
                confirmed = (
                    len(
                        confirmation_transcripts
                    ) >= desired
                    and support >= majority
                )
            else:
                support = 1

            if not confirmed:
                message = (
                    "Bekräftelsen var för osäker. "
                    'Säg tydligt "bekräfta" eller "avbryt".'
                )
                self._speak_control_message(message)
                return {
                    "status": "confirmation_required",
                    "message": message,
                    "transcript": pending["transcript"],
                    "confirmation_confidence": confidence,
                    "confirmation_transcripts": (
                        confirmation_transcripts
                    ),
                }

            current_risk = self._classify_risk(
                pending["transcript"]
            )
            pending_tools = set(
                pending["risk"].get(
                    "tool_names",
                    [],
                )
            )
            current_tools = set(
                current_risk.get(
                    "tool_names",
                    [],
                )
            )

            if (
                current_risk.get("level") == "high"
                and current_tools != pending_tools
            ):
                self.pending_confirmation = {
                    **pending,
                    "risk": current_risk,
                    "created_at": self.clock(),
                }
                message = (
                    "Den valda verktygsplanen ändrades efter bekräftelsen. "
                    'Säg "bekräfta" igen för den nya planen eller "avbryt".'
                )
                self._speak_control_message(message)
                return {
                    "status": "confirmation_required",
                    "message": message,
                    "transcript": pending["transcript"],
                    "risk": current_risk,
                }

            self.pending_confirmation = None
            response = self._respond_and_speak(
                pending["transcript"]
            )

            return {
                "status": "completed",
                "transcript": pending["transcript"],
                "risk": pending["risk"],
                "consensus": pending["consensus"],
                "assistant": response,
                "confirmation": {
                    "confirmed": True,
                    "heard": primary["text"],
                    "confidence": confidence,
                    "support": support,
                    "age_seconds": round(age, 3),
                },
            }

        message = (
            'Ett högriskkommando väntar. '
            'Säg "bekräfta" för att köra eller "avbryt".'
        )
        self._speak_control_message(message)
        return {
            "status": "confirmation_required",
            "message": message,
            "transcript": pending["transcript"],
            "heard": primary["text"],
        }

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

        pending_result = self._handle_pending_confirmation(
            primary,
            audio,
        )

        if pending_result is not None:
            return pending_result

        risk = self._classify_risk(
            primary["text"]
        )
        echo = self._probable_tts_echo(
            primary["text"],
            risk,
        )

        if echo is not None:
            return echo

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
                semantic_allowed = (
                    config.get(
                        "semantic_consensus_enabled",
                        False,
                    )
                    and self.semantic_resolver is not None
                    and (
                        risk["level"] != "high"
                        or config.get(
                            "semantic_consensus_for_high_risk",
                            False,
                        )
                    )
                )

                if semantic_allowed:
                    semantic = self.semantic_resolver.resolve(
                        [
                            item["text"]
                            for item in transcripts
                        ]
                    )

                    if semantic.get("accepted"):
                        consensus = {
                            **semantic,
                            "method": "semantic",
                            "transcripts": transcripts,
                        }
                    else:
                        return {
                            "status": "clarify",
                            "message": (
                                "Taligenkänningarna är inte tillräckligt "
                                "överens. Bekräfta eller säg kommandot igen."
                            ),
                            "risk": risk,
                            "consensus": {
                                **consensus,
                                "semantic": semantic,
                            },
                            "transcripts": transcripts,
                        }
                else:
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

        final_risk = self._classify_risk(
            transcript
        )

        if (
            final_risk["level"] == "high"
            and config.get(
                "high_risk_confirmation_enabled",
                False,
            )
        ):
            self.pending_confirmation = {
                "transcript": transcript,
                "risk": final_risk,
                "consensus": consensus,
                "created_at": self.clock(),
            }
            message = self._confirmation_message(
                transcript
            )
            self._speak_control_message(message)
            return {
                "status": "confirmation_required",
                "message": message,
                "transcript": transcript,
                "risk": final_risk,
                "consensus": consensus,
            }

        response = self._respond_and_speak(
            transcript
        )

        return {
            "status": "completed",
            "transcript": transcript,
            "risk": final_risk,
            "consensus": consensus,
            "assistant": response,
        }

    def interrupt(self):
        changed = self._stop_streaming_tts()

        if self.tts is None:
            return changed

        stop = getattr(
            self.tts,
            "stop",
            None,
        )

        if not callable(stop):
            return changed

        stop()
        return True
