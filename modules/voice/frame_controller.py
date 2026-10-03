from collections import deque

from modules.voice.vad import create_vad_from_settings


class VoiceFrameController:
    """Binder samman PCM-ramar, VAD, TTS-avbrott och VoiceSession."""

    def __init__(
        self,
        session,
        vad,
        pre_roll_frames=2,
        max_utterance_frames=1500,
    ):
        self.session = session
        self.vad = vad
        self.pre_roll = deque(
            maxlen=max(0, int(pre_roll_frames)),
        )
        self.max_utterance_frames = max(
            1,
            int(max_utterance_frames),
        )
        self.capturing = False
        self._frames = []

    def reset(self):
        self.pre_roll.clear()
        self.capturing = False
        self._frames = []
        self.vad.reset()

    def _complete_utterance(self, reason):
        audio = b"".join(self._frames)
        self._frames = []
        self.capturing = False
        self.pre_roll.clear()
        self.vad.reset()

        session_result = self.session.handle_audio(audio)

        return {
            "completed": True,
            "completion_reason": reason,
            "audio": audio,
            "session_result": session_result,
        }

    def process_frame(self, frame):
        vad_result = self.vad.process_frame(frame)
        event = vad_result["event"]
        output = {
            "event": event,
            "rms": vad_result["rms"],
            "completed": False,
            "completion_reason": None,
            "audio": None,
            "session_result": None,
            "interrupt_result": None,
        }

        if not self.capturing:
            if event == "speech_start":
                output["interrupt_result"] = (
                    self.session.interrupt()
                )
                self.capturing = True
                self._frames = list(self.pre_roll)
                self.pre_roll.clear()
                self._frames.append(frame)

                if len(self._frames) >= self.max_utterance_frames:
                    output.update(
                        self._complete_utterance(
                            "max_duration",
                        )
                    )
            else:
                self.pre_roll.append(frame)

            return output

        if event == "speech_end":
            output.update(
                self._complete_utterance(
                    "speech_end",
                )
            )
            return output

        self._frames.append(frame)

        if len(self._frames) >= self.max_utterance_frames:
            output.update(
                self._complete_utterance(
                    "max_duration",
                )
            )

        return output


def create_frame_controller(session, settings):
    config = settings.get("voice", {})
    frame_ms = max(
        1,
        int(config.get("vad_frame_ms", 20)),
    )
    max_seconds = max(
        1.0,
        float(
            config.get(
                "max_utterance_seconds",
                30,
            )
        ),
    )
    max_frames = max(
        1,
        int(
            (max_seconds * 1000) / frame_ms
        ),
    )

    return VoiceFrameController(
        session=session,
        vad=create_vad_from_settings(settings),
        pre_roll_frames=config.get(
            "vad_pre_roll_frames",
            2,
        ),
        max_utterance_frames=max_frames,
    )
