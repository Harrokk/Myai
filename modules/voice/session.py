from modules.voice.consensus import choose_transcript_consensus


class VoiceSession:
    """Hårdvaruoberoende röstorkestrering runt MyAI-kärnan."""

    def __init__(
        self,
        assistant_core,
        stt_engines,
        tts_engine=None,
        settings=None,
    ):
        self.assistant_core = assistant_core
        self.stt_engines = list(stt_engines or [])
        self.tts_engine = tts_engine
        self.settings = settings or {}

    @property
    def voice_config(self):
        return self.settings.get("voice", {})

    def _transcribe(self, engine, audio):
        result = engine.transcribe(audio)

        if isinstance(result, str):
            result = {
                "text": result,
                "confidence": 0.0,
                "uncertain_words": 0,
            }

        if not isinstance(result, dict):
            raise ValueError(
                "STT-motorn måste returnera text eller ett resultatobjekt."
            )

        return {
            "text": str(result.get("text") or "").strip(),
            "confidence": float(
                result.get("confidence", 0.0) or 0.0
            ),
            "uncertain_words": int(
                result.get("uncertain_words", 0) or 0
            ),
            "provider": (
                result.get("provider")
                or getattr(engine, "name", engine.__class__.__name__)
            ),
        }

    def collect_transcripts(self, audio):
        if not self.stt_engines:
            return {
                "decision": {
                    "status": "clarify",
                    "text": None,
                    "risk": "normal",
                    "agreement_count": 0,
                    "reason": "Ingen STT-motor är konfigurerad.",
                },
                "transcripts": [],
            }

        max_interpretations = max(
            1,
            min(
                int(
                    self.voice_config.get(
                        "max_interpretations",
                        3,
                    )
                ),
                3,
                len(self.stt_engines),
            ),
        )

        transcripts = []

        for index, engine in enumerate(
            self.stt_engines[:max_interpretations]
        ):
            transcript = self._transcribe(
                engine,
                audio,
            )
            transcripts.append(transcript)

            decision = choose_transcript_consensus(
                transcripts,
                self.settings,
            )

            if decision["status"] == "accepted":
                return {
                    "decision": decision,
                    "transcripts": transcripts,
                }

            if (
                decision["status"] == "clarify"
                and index + 1 >= max_interpretations
            ):
                return {
                    "decision": decision,
                    "transcripts": transcripts,
                }

        decision = choose_transcript_consensus(
            transcripts,
            self.settings,
        )

        return {
            "decision": decision,
            "transcripts": transcripts,
        }

    def handle_audio(self, audio):
        if not self.voice_config.get("enabled", False):
            return {
                "status": "disabled",
                "reason": "Röstfunktionen är avstängd.",
                "transcripts": [],
                "decision": None,
                "assistant_result": None,
                "spoken": False,
            }

        collected = self.collect_transcripts(audio)
        decision = collected["decision"]

        if decision["status"] != "accepted":
            return {
                "status": decision["status"],
                "reason": decision.get("reason"),
                "transcripts": collected["transcripts"],
                "decision": decision,
                "assistant_result": None,
                "spoken": False,
            }

        assistant_result = self.assistant_core.respond(
            decision["text"]
        )
        answer = assistant_result.get("answer", "")
        spoken = False
        tts_error = None

        if (
            self.tts_engine is not None
            and self.voice_config.get(
                "speak_responses",
                True,
            )
            and answer
        ):
            try:
                self.tts_engine.speak(answer)
                spoken = True
            except Exception as error:
                tts_error = str(error)

        return {
            "status": "completed",
            "reason": None,
            "transcripts": collected["transcripts"],
            "decision": decision,
            "assistant_result": assistant_result,
            "spoken": spoken,
            "tts_error": tts_error,
        }

    def interrupt(self):
        if self.tts_engine is None:
            return {
                "stopped": False,
                "reason": "Ingen TTS-motor är konfigurerad.",
            }

        stop = getattr(self.tts_engine, "stop", None)

        if not callable(stop):
            return {
                "stopped": False,
                "reason": "TTS-motorn stöder inte avbrott.",
            }

        stop()
        return {
            "stopped": True,
            "reason": "Pågående uppläsning stoppades.",
        }
