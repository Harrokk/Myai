import gc
from pathlib import Path
import tempfile
import wave


class SoundDeviceMicrophone:
    def __init__(
        self,
        sample_rate=16000,
        channels=1,
        frame_ms=20,
        device=None,
        module=None,
    ):
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.frame_ms = int(frame_ms)
        self.device = device
        self._module = module
        self._stream = None

    @property
    def frame_samples(self):
        return int(
            self.sample_rate
            * self.frame_ms
            / 1000
        )

    def _sounddevice(self):
        if self._module is not None:
            return self._module

        try:
            import sounddevice
        except ImportError as error:
            raise RuntimeError(
                "Mikrofon kräver sounddevice. "
                "Installera requirements-voice.txt."
            ) from error

        return sounddevice

    def start(self):
        if self._stream is not None:
            return False

        sd = self._sounddevice()
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.frame_samples,
            device=self.device,
        )
        self._stream.start()
        return True

    def read_frame(self):
        if self._stream is None:
            raise RuntimeError("Mikrofonen är inte startad.")

        data, overflowed = self._stream.read(
            self.frame_samples
        )

        return {
            "frame": bytes(data),
            "overflowed": bool(overflowed),
        }

    def stop(self):
        if self._stream is None:
            return False

        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

        return True


class WebRTCVADProvider:
    def __init__(
        self,
        aggressiveness=2,
        sample_rate=16000,
        module=None,
    ):
        self.sample_rate = int(sample_rate)
        self._module = module

        if module is None:
            try:
                import webrtcvad
            except ImportError as error:
                raise RuntimeError(
                    "VAD kräver webrtcvad-wheels. "
                    "Installera requirements-voice.txt."
                ) from error

            module = webrtcvad

        self._vad = module.Vad(
            int(aggressiveness)
        )

    def is_speech(self, frame):
        if not isinstance(
            frame,
            (bytes, bytearray, memoryview),
        ):
            raise ValueError(
                "WebRTC VAD kräver PCM-bytes."
            )

        return bool(
            self._vad.is_speech(
                bytes(frame),
                self.sample_rate,
            )
        )


class FasterWhisperSTT:
    def __init__(
        self,
        model_name="small",
        device="auto",
        compute_type="default",
        language="sv",
        sample_rate=16000,
        channels=1,
        sample_width=2,
        model=None,
        module=None,
    ):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.sample_width = int(sample_width)
        self._model = model
        self._module = module

    def _load_model(self):
        if self._model is not None:
            return self._model

        module = self._module

        if module is None:
            try:
                import faster_whisper as module
            except ImportError as error:
                raise RuntimeError(
                    "STT kräver faster-whisper. "
                    "Installera requirements-voice.txt."
                ) from error

        self._model = module.WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )
        return self._model

    def _write_temp_wav(self, audio):
        if not isinstance(
            audio,
            (bytes, bytearray, memoryview),
        ):
            return None

        handle = tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        )
        path = Path(handle.name)
        handle.close()

        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(self.sample_width)
            wav.setframerate(self.sample_rate)
            wav.writeframes(bytes(audio))

        return path

    def transcribe(self, audio):
        model = self._load_model()
        temporary = self._write_temp_wav(
            audio
        )

        try:
            source = (
                str(temporary)
                if temporary is not None
                else audio
            )
            segments, info = model.transcribe(
                source,
                language=self.language,
                vad_filter=False,
            )
            segment_list = list(segments)
            text = " ".join(
                str(
                    getattr(
                        segment,
                        "text",
                        "",
                    )
                ).strip()
                for segment in segment_list
                if str(
                    getattr(
                        segment,
                        "text",
                        "",
                    )
                ).strip()
            ).strip()

            return {
                "text": text,
                "confidence": None,
                "language": getattr(
                    info,
                    "language",
                    self.language,
                ),
            }
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass


    def release_for_inference(self):
        """Release the loaded STT model before another heavy model is activated."""
        if self._model is None:
            return False

        self._model = None
        gc.collect()
        return True


class Pyttsx3TTS:
    def __init__(
        self,
        rate=180,
        volume=1.0,
        voice_id=None,
        engine=None,
        module=None,
    ):
        self.rate = int(rate)
        self.volume = max(
            0.0,
            min(float(volume), 1.0),
        )
        self.voice_id = voice_id
        self._engine = engine
        self._module = module

    def _get_engine(self):
        if self._engine is not None:
            return self._engine

        module = self._module

        if module is None:
            try:
                import pyttsx3 as module
            except ImportError as error:
                raise RuntimeError(
                    "TTS kräver pyttsx3. "
                    "Installera requirements-voice.txt."
                ) from error

        self._engine = module.init()
        self._engine.setProperty(
            "rate",
            self.rate,
        )
        self._engine.setProperty(
            "volume",
            self.volume,
        )

        if self.voice_id:
            self._engine.setProperty(
                "voice",
                self.voice_id,
            )

        return self._engine

    def speak(self, text):
        value = str(text or "").strip()

        if not value:
            return False

        engine = self._get_engine()
        engine.say(value)
        engine.runAndWait()
        return True

    def stop(self):
        if self._engine is None:
            return False

        self._engine.stop()
        return True
