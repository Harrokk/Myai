"""Opt-in adapter from Silero's speech segments to MyAI's voice pipeline.

Silero produces *complete audio segments*, not per-frame boolean decisions.
Keep this separate from the default WebRTC-VAD VoiceStreamController.
Neither provider nor audio devices are constructed by this class.
"""


class SileroVoiceStreamController:
    MAX_PCM_BYTES = 13 * 16000 * 2

    def __init__(self, *, vad, pipeline, before_process=None, after_process=None):
        if not all(callable(getattr(vad, name, None))
                   for name in ("feed", "reset", "is_speech_detected")):
            raise ValueError("Silero segment provider contract required")
        self.vad = vad
        self.pipeline = pipeline
        self.before_process = before_process
        self.after_process = after_process
        self._speaking = False

    def reset(self):
        self._speaking = False
        self.vad.reset()

    def feed_frame(self, frame):
        segments = self.vad.feed(frame)
        if not isinstance(segments, (list, tuple)):
            raise ValueError("Invalid Silero segment collection")
        if len(segments) > 1:
            # The outer VoiceSession consumes one utterance per run_once().
            # Never silently discard additional audio or duplicate tool calls.
            raise ValueError("Multiple Silero segments in one frame are unsupported")
        if segments:
            audio = segments[0]
            if (not isinstance(audio, bytes)
                    or not 0 < len(audio) <= self.MAX_PCM_BYTES
                    or len(audio) % 2):
                raise ValueError("Invalid Silero PCM utterance")
            if not self._speaking:
                # A very short segment can finish before the Python caller
                # sees an active speech flag. The first segment still has
                # to cancel earlier TTS before any new utterance.
                self.pipeline.interrupt()
            try:
                if self.before_process is not None:
                    self.before_process()
                try:
                    result = self.pipeline.process_utterance(audio)
                finally:
                    if self.after_process is not None:
                        self.after_process()
                return {
                    "type": "utterance_complete",
                    "reason": "silero_endpoint",
                    "pipeline_result": result,
                }
            finally:
                # Prevent cross-utterance PCM state and duplicate completion.
                self.reset()

        speaking = bool(self.vad.is_speech_detected())
        if speaking and not self._speaking:
            self._speaking = True
            return {
                "type": "speech_started",
                "tts_interrupted": self.pipeline.interrupt(),
            }
        if not speaking:
            self._speaking = False
        return None
