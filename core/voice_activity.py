class VoiceActivityGate:
    def __init__(
        self,
        start_speech_frames=2,
        end_silence_frames=3,
        max_frames=500,
    ):
        self.start_speech_frames = max(
            1,
            int(start_speech_frames),
        )
        self.end_silence_frames = max(
            1,
            int(end_silence_frames),
        )
        self.max_frames = max(
            self.start_speech_frames,
            int(max_frames),
        )
        self.reset()

    def reset(self):
        self._state = "idle"
        self._speech_run = 0
        self._silence_run = 0
        self._frames = []
        self._pre_speech = []

    @property
    def state(self):
        return self._state

    def feed(self, frame, is_speech):
        if frame is None:
            raise ValueError("Ljudram saknas.")

        if not isinstance(is_speech, bool):
            raise ValueError("is_speech måste vara bool.")

        event = None

        if self._state == "idle":
            if is_speech:
                self._speech_run += 1
                self._pre_speech.append(frame)

                if self._speech_run >= self.start_speech_frames:
                    self._state = "speaking"
                    self._frames.extend(
                        self._pre_speech
                    )
                    self._pre_speech = []
                    self._silence_run = 0
                    event = {
                        "type": "speech_started",
                    }
            else:
                self._speech_run = 0
                self._pre_speech = []

            return event

        self._frames.append(frame)

        if is_speech:
            self._silence_run = 0
        else:
            self._silence_run += 1

        if len(self._frames) >= self.max_frames:
            return self._finish(
                reason="max_length",
            )

        if self._silence_run >= self.end_silence_frames:
            return self._finish(
                reason="silence",
            )

        return event

    def _finish(self, reason):
        frames = list(self._frames)
        self.reset()
        return {
            "type": "utterance_complete",
            "reason": reason,
            "frames": frames,
        }


class VoiceStreamController:
    def __init__(
        self,
        vad,
        gate,
        pipeline,
    ):
        self.vad = vad
        self.gate = gate
        self.pipeline = pipeline

    def feed_frame(self, frame):
        is_speech = bool(
            self.vad.is_speech(frame)
        )
        event = self.gate.feed(
            frame,
            is_speech,
        )

        if event is None:
            return None

        if event["type"] == "speech_started":
            interrupted = self.pipeline.interrupt()
            return {
                **event,
                "tts_interrupted": interrupted,
            }

        if event["type"] == "utterance_complete":
            audio = b"".join(
                event["frames"]
            )
            result = self.pipeline.process_utterance(
                audio
            )
            return {
                **event,
                "pipeline_result": result,
            }

        return event
