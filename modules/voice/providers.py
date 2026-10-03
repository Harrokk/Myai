import base64
import math
import os
import platform
import subprocess
import tempfile
import wave


class FasterWhisperSTT:
    def __init__(
        self,
        model_name="small",
        device="auto",
        compute_type="auto",
        language="sv",
        beam_size=5,
        sample_rate=16000,
        uncertain_word_probability=0.60,
        model_factory=None,
    ):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = max(1, int(beam_size))
        self.sample_rate = int(sample_rate)
        self.uncertain_word_probability = float(
            uncertain_word_probability
        )
        self.model_factory = model_factory
        self._model = None
        self.name = (
            f"faster-whisper:{model_name}:beam{self.beam_size}"
        )

    def _load_model(self):
        if self._model is not None:
            return self._model

        factory = self.model_factory

        if factory is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as error:
                raise RuntimeError(
                    "Faster-Whisper är inte installerat. "
                    "Installera requirements-voice-stt.txt."
                ) from error

            factory = WhisperModel

        self._model = factory(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )
        return self._model

    def _write_pcm_wav(self, audio):
        if not isinstance(audio, (bytes, bytearray)):
            raise TypeError(
                "STT-ljud måste vara mono PCM16 bytes."
            )

        if len(audio) % 2:
            raise ValueError(
                "PCM16-ljudet innehåller ett ofullständigt sample."
            )

        handle = tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        )
        path = handle.name
        handle.close()

        try:
            with wave.open(path, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.sample_rate)
                wav.writeframes(bytes(audio))
        except Exception:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise

        return path

    def transcribe(self, audio):
        path = self._write_pcm_wav(audio)

        try:
            model = self._load_model()
            segments, _info = model.transcribe(
                path,
                language=self.language or None,
                beam_size=self.beam_size,
                word_timestamps=True,
            )
            segments = list(segments)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

        text_parts = []
        word_probabilities = []
        segment_probabilities = []

        for segment in segments:
            text = str(
                getattr(segment, "text", "") or ""
            ).strip()

            if text:
                text_parts.append(text)

            words = getattr(segment, "words", None) or []

            for word in words:
                probability = getattr(
                    word,
                    "probability",
                    None,
                )

                if probability is not None:
                    word_probabilities.append(
                        max(
                            0.0,
                            min(float(probability), 1.0),
                        )
                    )

            avg_logprob = getattr(
                segment,
                "avg_logprob",
                None,
            )

            if avg_logprob is not None:
                segment_probabilities.append(
                    max(
                        0.0,
                        min(
                            math.exp(float(avg_logprob)),
                            1.0,
                        ),
                    )
                )

        if word_probabilities:
            confidence = sum(word_probabilities) / len(
                word_probabilities
            )
            uncertain_words = sum(
                probability
                < self.uncertain_word_probability
                for probability in word_probabilities
            )
        elif segment_probabilities:
            confidence = sum(segment_probabilities) / len(
                segment_probabilities
            )
            uncertain_words = 0
        else:
            confidence = 0.0
            uncertain_words = 0

        return {
            "text": " ".join(text_parts).strip(),
            "confidence": round(confidence, 4),
            "uncertain_words": uncertain_words,
            "provider": self.name,
        }


class WindowsSapiTTS:
    def __init__(
        self,
        voice_name="",
        rate=0,
        volume=100,
        popen_factory=None,
    ):
        self.voice_name = (voice_name or "").strip()
        self.rate = max(-10, min(int(rate), 10))
        self.volume = max(0, min(int(volume), 100))
        self.popen_factory = (
            popen_factory or subprocess.Popen
        )
        self._process = None
        self.name = "windows_sapi"

    @staticmethod
    def _encode(value):
        return base64.b64encode(
            str(value).encode("utf-8")
        ).decode("ascii")

    def _script(self, text):
        text64 = self._encode(text)
        parts = [
            "Add-Type -AssemblyName System.Speech",
            (
                "$s=New-Object "
                "System.Speech.Synthesis.SpeechSynthesizer"
            ),
            f"$s.Rate={self.rate}",
            f"$s.Volume={self.volume}",
        ]

        if self.voice_name:
            voice64 = self._encode(self.voice_name)
            parts.extend(
                [
                    (
                        "$vb=[Convert]::FromBase64String("
                        f"'{voice64}')"
                    ),
                    (
                        "$vn=[Text.Encoding]::UTF8.GetString("
                        "$vb)"
                    ),
                    "$s.SelectVoice($vn)",
                ]
            )

        parts.extend(
            [
                (
                    "$tb=[Convert]::FromBase64String("
                    f"'{text64}')"
                ),
                "$t=[Text.Encoding]::UTF8.GetString($tb)",
                "$s.Speak($t)",
            ]
        )
        return "; ".join(parts)

    def speak(self, text):
        value = str(text or "").strip()

        if not value:
            return False

        self.stop()
        self._process = self.popen_factory(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                self._script(value),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True

    def stop(self):
        process = self._process

        if process is None:
            return False

        try:
            running = process.poll() is None
        except Exception:
            running = True

        if running:
            process.terminate()

            try:
                process.wait(timeout=1)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

        self._process = None
        return running


def build_stt_engines(settings):
    config = settings.get("voice", {})
    provider = (
        config.get("stt_provider") or ""
    ).strip().lower()

    if not provider:
        return []

    if provider != "faster_whisper":
        raise ValueError(
            f"Okänd STT-provider: {provider}"
        )

    profiles = config.get("stt_profiles") or [{}]
    engines = []

    for profile in profiles[
        : max(
            1,
            min(
                int(
                    config.get(
                        "max_interpretations",
                        3,
                    )
                ),
                3,
            ),
        )
    ]:
        profile = profile or {}
        engines.append(
            FasterWhisperSTT(
                model_name=profile.get(
                    "model",
                    config.get(
                        "stt_model",
                        "small",
                    ),
                ),
                device=profile.get(
                    "device",
                    config.get(
                        "stt_device",
                        "auto",
                    ),
                ),
                compute_type=profile.get(
                    "compute_type",
                    config.get(
                        "stt_compute_type",
                        "auto",
                    ),
                ),
                language=profile.get(
                    "language",
                    config.get(
                        "stt_language",
                        "sv",
                    ),
                ),
                beam_size=profile.get(
                    "beam_size",
                    config.get(
                        "stt_beam_size",
                        5,
                    ),
                ),
                sample_rate=config.get(
                    "vad_sample_rate",
                    16000,
                ),
                uncertain_word_probability=config.get(
                    "stt_uncertain_word_probability",
                    0.60,
                ),
            )
        )

    return engines


def build_tts_engine(settings):
    config = settings.get("voice", {})
    provider = (
        config.get("tts_provider") or ""
    ).strip().lower()

    if not provider:
        return None

    if provider != "windows_sapi":
        raise ValueError(
            f"Okänd TTS-provider: {provider}"
        )

    if platform.system().lower() != "windows":
        raise RuntimeError(
            "Windows SAPI TTS kan endast användas på Windows."
        )

    return WindowsSapiTTS(
        voice_name=config.get(
            "tts_voice_name",
            "",
        ),
        rate=config.get(
            "tts_rate",
            0,
        ),
        volume=config.get(
            "tts_volume",
            100,
        ),
    )
