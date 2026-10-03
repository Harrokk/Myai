from modules.voice.frame_controller import create_frame_controller
from modules.voice.microphone import build_microphone
from modules.voice.providers import (
    build_stt_engines,
    build_tts_engine,
)
from modules.voice.session import VoiceSession


class VoiceRuntime:
    """Sammanhållen livscykel för MyAI:s modulära röstkedja."""

    def __init__(
        self,
        assistant_core,
        settings,
        stt_engines=None,
        tts_engine=None,
        session=None,
        controller=None,
        microphone=None,
        sounddevice_module=None,
    ):
        self.assistant_core = assistant_core
        self.settings = settings
        self.voice_config = settings.get("voice", {})
        self.completed_results = []
        self.last_frame_result = None

        self.stt_engines = (
            list(stt_engines)
            if stt_engines is not None
            else build_stt_engines(settings)
        )
        self.tts_engine = (
            tts_engine
            if tts_engine is not None
            else build_tts_engine(settings)
        )
        self.session = (
            session
            if session is not None
            else VoiceSession(
                assistant_core=assistant_core,
                stt_engines=self.stt_engines,
                tts_engine=self.tts_engine,
                settings=settings,
            )
        )
        self.controller = (
            controller
            if controller is not None
            else create_frame_controller(
                self.session,
                settings,
            )
        )
        self.microphone = (
            microphone
            if microphone is not None
            else build_microphone(
                self.controller,
                settings,
                sounddevice_module=sounddevice_module,
                result_callback=self._on_frame_result,
            )
        )
        self.running = False

    def _on_frame_result(self, result):
        self.last_frame_result = result

        if result.get("completed"):
            self.completed_results.append(result)

    def status(self):
        return {
            "enabled": bool(
                self.voice_config.get("enabled", False)
            ),
            "running": self.running,
            "microphone_configured": self.microphone is not None,
            "stt_engine_count": len(self.stt_engines),
            "tts_configured": self.tts_engine is not None,
            "completed_utterances": len(
                self.completed_results
            ),
        }

    def start(self):
        if not self.voice_config.get("enabled", False):
            return {
                "started": False,
                "reason": "Röstfunktionen är avstängd.",
                "status": self.status(),
            }

        if self.microphone is None:
            return {
                "started": False,
                "reason": "Ingen mikrofonprovider är konfigurerad.",
                "status": self.status(),
            }

        if not self.stt_engines:
            return {
                "started": False,
                "reason": "Ingen STT-provider är konfigurerad.",
                "status": self.status(),
            }

        started = self.microphone.start()
        self.running = bool(started or self.microphone.stream is not None)

        return {
            "started": self.running,
            "reason": None if self.running else "Mikrofonströmmen startade inte.",
            "status": self.status(),
        }

    def stop(self):
        microphone_stopped = False

        if self.microphone is not None:
            microphone_stopped = self.microphone.stop()

        interrupt_result = self.session.interrupt()
        was_running = self.running
        self.running = False

        return {
            "stopped": bool(
                was_running
                or microphone_stopped
                or interrupt_result.get("stopped")
            ),
            "microphone_stopped": microphone_stopped,
            "tts_interrupt": interrupt_result,
            "status": self.status(),
        }

    def clear_completed_results(self):
        self.completed_results = []


def build_voice_runtime(
    assistant_core,
    settings,
    sounddevice_module=None,
):
    return VoiceRuntime(
        assistant_core=assistant_core,
        settings=settings,
        sounddevice_module=sounddevice_module,
    )
