import math
import struct


def pcm16_rms(frame):
    if not isinstance(frame, (bytes, bytearray)):
        raise TypeError("PCM-ramen måste vara bytes.")

    if len(frame) % 2:
        raise ValueError("PCM16-ramen måste innehålla hela 16-bitars samples.")

    if not frame:
        return 0.0

    sample_count = len(frame) // 2
    samples = struct.unpack(
        "<" + "h" * sample_count,
        frame,
    )
    mean_square = sum(
        sample * sample
        for sample in samples
    ) / sample_count

    return math.sqrt(mean_square)


class VoiceActivityDetector:
    """Enkel energi-baserad VAD för mono PCM16."""

    def __init__(
        self,
        rms_threshold=500,
        start_frames=2,
        end_silence_frames=8,
    ):
        self.rms_threshold = float(rms_threshold)
        self.start_frames = max(1, int(start_frames))
        self.end_silence_frames = max(
            1,
            int(end_silence_frames),
        )
        self.speaking = False
        self._active_run = 0
        self._silence_run = 0

    def reset(self):
        self.speaking = False
        self._active_run = 0
        self._silence_run = 0

    def process_frame(self, frame):
        rms = pcm16_rms(frame)
        active = rms >= self.rms_threshold

        if not self.speaking:
            if active:
                self._active_run += 1

                if self._active_run >= self.start_frames:
                    self.speaking = True
                    self._silence_run = 0
                    return {
                        "event": "speech_start",
                        "speech": True,
                        "rms": round(rms, 2),
                    }
            else:
                self._active_run = 0

            return {
                "event": "silence",
                "speech": False,
                "rms": round(rms, 2),
            }

        if active:
            self._silence_run = 0
            return {
                "event": "speech",
                "speech": True,
                "rms": round(rms, 2),
            }

        self._silence_run += 1

        if self._silence_run >= self.end_silence_frames:
            self.speaking = False
            self._active_run = 0
            self._silence_run = 0
            return {
                "event": "speech_end",
                "speech": False,
                "rms": round(rms, 2),
            }

        return {
            "event": "speech",
            "speech": True,
            "rms": round(rms, 2),
        }


def create_vad_from_settings(settings):
    config = settings.get("voice", {})

    return VoiceActivityDetector(
        rms_threshold=config.get(
            "vad_rms_threshold",
            500,
        ),
        start_frames=config.get(
            "vad_start_frames",
            2,
        ),
        end_silence_frames=config.get(
            "vad_end_silence_frames",
            8,
        ),
    )
