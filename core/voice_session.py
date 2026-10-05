import time

from core.config import load_settings
from core.voice_activity import VoiceActivityGate, VoiceStreamController
from core.voice_factory import build_voice_components
from core.voice_pipeline import VoicePipeline
from core.voice_semantic import SemanticConsensusResolver


class VoiceSession:
    def __init__(
        self,
        assistant,
        settings=None,
        components=None,
        semantic_resolver=None,
        llm_client=None,
        sleep_fn=None,
    ):
        self.assistant = assistant
        self.settings = settings or load_settings()
        self.voice = self.settings.get("voice", {})
        self.components = (
            components
            if components is not None
            else build_voice_components(self.settings)
        )
        self.running = False
        self.frame_count = 0
        self.overflow_count = 0
        self._sleep = sleep_fn or time.sleep
        self.microphone_paused_for_inference = False

        if semantic_resolver is None and self.voice.get(
            "semantic_consensus_enabled",
            False,
        ):
            active_llm = (
                llm_client
                or getattr(
                    assistant,
                    "llm",
                    None,
                )
            )

            if active_llm is not None:
                semantic_resolver = SemanticConsensusResolver(
                    active_llm,
                    min_confidence=self.voice.get(
                        "semantic_consensus_min_confidence",
                        0.85,
                    ),
                )

        self.semantic_resolver = semantic_resolver

        self.gate = VoiceActivityGate(
            start_speech_frames=self.voice.get(
                "vad_start_speech_frames",
                2,
            ),
            end_silence_frames=self.voice.get(
                "vad_end_silence_frames",
                3,
            ),
            max_frames=self.voice.get(
                "vad_max_frames",
                500,
            ),
        )

        if self.components.get("enabled"):
            self.pipeline = VoicePipeline(
                assistant,
                self.components["primary_stt"],
                backup_stt=self.components.get(
                    "backup_stt",
                    [],
                ),
                tts=self.components.get("tts"),
                settings=self.settings,
                semantic_resolver=semantic_resolver,
                before_assistant=self._before_model_inference,
            )
            self.controller = VoiceStreamController(
                vad=self.components["vad"],
                gate=self.gate,
                pipeline=self.pipeline,
                before_process=self._before_inference,
                after_process=self._after_inference,
            )
        else:
            self.pipeline = None
            self.controller = None

    @property
    def enabled(self):
        return bool(
            self.components.get("enabled")
        )

    def status(self):
        if not self.enabled:
            return {
                "enabled": False,
                "running": False,
            }

        return {
            "enabled": True,
            "running": self.running,
            "microphone_paused_for_inference": (
                self.microphone_paused_for_inference
            ),
            "microphone": type(
                self.components["microphone"]
            ).__name__,
            "vad": type(
                self.components["vad"]
            ).__name__,
            "primary_stt": type(
                self.components["primary_stt"]
            ).__name__,
            "backup_stt_count": len(
                self.components.get(
                    "backup_stt",
                    [],
                )
            ),
            "tts": (
                type(
                    self.components["tts"]
                ).__name__
                if self.components.get("tts")
                is not None
                else None
            ),
            "semantic_consensus": (
                self.semantic_resolver
                is not None
            ),
        }

    def _before_inference(self):
        if not self.voice.get(
            "release_microphone_during_inference",
            False,
        ):
            return False

        if (
            not self.running
            or self.microphone_paused_for_inference
        ):
            return False

        stopped = self.components[
            "microphone"
        ].stop()

        if stopped is False:
            raise RuntimeError(
                "Mikrofonen kunde inte frigöras före AI-inference."
            )

        self.microphone_paused_for_inference = True
        return True

    def _before_model_inference(self):
        if self.voice.get(
            "release_stt_before_model",
            False,
        ):
            providers = [
                self.components.get(
                    "primary_stt"
                ),
                *self.components.get(
                    "backup_stt",
                    [],
                ),
            ]

            for provider in providers:
                release = getattr(
                    provider,
                    "release_for_inference",
                    None,
                )

                if callable(release):
                    release()

        delay = max(
            0.0,
            float(
                self.voice.get(
                    "model_handoff_delay_seconds",
                    0.0,
                )
            ),
        )

        if delay > 0:
            self._sleep(delay)

        return True

    def _after_inference(self):
        if not self.microphone_paused_for_inference:
            return False

        self.microphone_paused_for_inference = False

        if not self.running:
            return False

        started = self.components[
            "microphone"
        ].start()

        if started is False:
            raise RuntimeError(
                "Mikrofonen kunde inte återstartas efter AI-inference."
            )

        return True

    def start(self):
        if not self.enabled:
            raise RuntimeError(
                "Röstläge är avstängt i konfigurationen."
            )

        if self.running:
            return False

        self.components["microphone"].start()
        self.running = True
        return True

    def stop(self):
        if not self.enabled:
            return False

        changed = False

        if self.pipeline is not None:
            changed = (
                self.pipeline.interrupt()
                or changed
            )

        if self.running:
            if not self.microphone_paused_for_inference:
                self.components["microphone"].stop()

            self.running = False
            self.microphone_paused_for_inference = False
            changed = True

        self.gate.reset()
        return changed

    def run_once(
        self,
        max_wait_frames=None,
    ):
        if not self.enabled:
            return {
                "status": "disabled",
                "message": (
                    "Röstläge är avstängt i konfigurationen."
                ),
            }

        if not self.running:
            self.start()

        limit = max(
            1,
            int(
                max_wait_frames
                or self.voice.get(
                    "session_max_wait_frames",
                    1500,
                )
            ),
        )
        read_count = 0

        while read_count < limit:
            item = self.components[
                "microphone"
            ].read_frame()
            read_count += 1
            self.frame_count += 1

            if item.get("overflowed"):
                self.overflow_count += 1

            event = self.controller.feed_frame(
                item["frame"]
            )

            if (
                event is not None
                and event.get("type")
                == "utterance_complete"
            ):
                return {
                    "status": "utterance_complete",
                    "frames_read": read_count,
                    "overflow_count": self.overflow_count,
                    "voice_result": event.get(
                        "pipeline_result"
                    ),
                    "end_reason": event.get(
                        "reason"
                    ),
                }

        self.gate.reset()
        return {
            "status": "timeout",
            "frames_read": read_count,
            "overflow_count": self.overflow_count,
            "message": (
                "Ingen komplett talfras upptäcktes inom tidsgränsen."
            ),
        }
