"""Opt-in Swedish Piper Alma TTS and explicitly selected sound output.

Pinned Alma weights are loaded from local disk on FIRST synthesis only.
No model download, microphone, speaker open, network request or inference
at import/construction time. Voice and output device must be explicitly set.
"""

import gc
import hashlib
import io
import json
import math
import threading
import wave
from pathlib import Path


_ALMA_SHA256 = "f75455eb6afeb1db9e2905d5bd7e4115afcd3710e0d399b6a40981766d32fedc"
_ALMA_BASENAME = "sv_SE-alma-medium.onnx"


class SoundDeviceWavSink:
    """Play only bounded 22,050-Hz, mono PCM16 WAV to an explicit device."""

    def __init__(self, device, *, module=None):
        if (type(device) is int and device >= 0):
            pass
        elif isinstance(device, str) and 0 < len(device) <= 120:
            pass
        else:
            raise ValueError("Explicit sound output device required")
        self.device = device
        self._module = module
        self._stream = None
        self._lock = threading.Lock()
        self._cancel = threading.Event()

    def play_wav(self, wav_data):
        if not isinstance(wav_data, (bytes, bytearray)):
            raise TypeError("Piper output must be WAV bytes")
        if not 44 <= len(wav_data) <= 1_000_000:
            raise ValueError("Piper output size invalid")
        with wave.open(io.BytesIO(wav_data), "rb") as reader:
            if (reader.getnchannels() != 1 or reader.getsampwidth() != 2
                    or reader.getframerate() != 22050
                    or not 0 < reader.getnframes() <= 22050 * 20):
                raise ValueError("Piper requires bounded mono 22kHz PCM16")
            if self._cancel.is_set():
                return False
            audio_module = self._module
            if audio_module is None:
                import sounddevice as audio_module
            stream = audio_module.RawOutputStream(
                samplerate=22050, channels=1, dtype="int16",
                device=self.device, blocksize=1024,
            )
            with self._lock:
                if self._cancel.is_set():
                    stream.close()
                    return False
                self._stream = stream
            try:
                stream.start()
                while not self._cancel.is_set():
                    chunk = reader.readframes(1024)
                    if not chunk:
                        break
                    stream.write(chunk)
            finally:
                try:
                    stream.stop()
                finally:
                    stream.close()
                    with self._lock:
                        if self._stream is stream:
                            self._stream = None
            return not self._cancel.is_set()

    def reset(self):
        self._cancel.clear()

    def stop(self):
        self._cancel.set()
        with self._lock:
            stream = self._stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                raise RuntimeError("Sound output could not be interrupted") from None
        return True


class PiperAlmaTTS:
    """Synthesize a locally pinned Swedish voice, then play it only if selected."""

    def __init__(
        self, rate=180, volume=1.0, voice_id=None, output_device=None,
        *, voice=None, module=None, sink=None,
    ):
        if type(rate) is not int or not 110 <= rate <= 260:
            raise ValueError("Piper speech rate must be 110-260")
        if (type(volume) not in (int, float) or
                not math.isfinite(volume) or not 0 <= volume <= 1):
            raise ValueError("Piper volume must be finite in [0,1]")
        self.rate = rate
        self.volume = float(volume)
        self.voice_id = voice_id
        self._voice = voice
        self._module = module
        self._sink = sink if sink is not None else (
            SoundDeviceWavSink(output_device)
            if output_device is not None else None
        )
        self._cancel = threading.Event()
        self._render_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._generation = 0

    def _verified_voice_path(self):
        name = self.voice_id
        if not isinstance(name, str) or not name or "\x00" in name or len(name) > 512:
            raise RuntimeError("Piper requires the pinned local Alma voice")
        path = Path(name)
        sidecar = Path(str(path) + ".json")
        if (not path.is_absolute() or path.name != _ALMA_BASENAME
                or path.is_symlink() or sidecar.is_symlink()
                or not path.is_file() or not sidecar.is_file()
                or not 55_000_000 <= path.stat().st_size <= 70_000_000):
            raise RuntimeError("Piper Alma voice is missing or incomplete")
        try:
            with path.open("rb") as handle:
                sha = hashlib.file_digest(handle, "sha256").hexdigest()
            if sha != _ALMA_SHA256:
                raise ValueError
            if not 4000 <= sidecar.stat().st_size <= 14000:
                raise ValueError
            config = json.loads(sidecar.read_text(encoding="utf-8"))
            if (config.get("dataset") != "alma"
                    or config.get("language", {}).get("code") != "sv_SE"
                    or config.get("audio", {}).get("sample_rate") != 22050
                    or config.get("espeak", {}).get("voice") != "sv"):
                raise ValueError
        except (OSError, ValueError, TypeError, AttributeError):
            raise RuntimeError("Piper Alma model integrity verification failed") from None
        return path

    def _load_voice(self):
        if self._voice is not None:
            return self._voice
        model = self._verified_voice_path()
        try:
            module = self._module
            if module is None:
                import piper as module
            self._voice = module.PiperVoice.load(str(model))
        except Exception:
            raise RuntimeError("Piper voice initialization failed") from None
        return self._voice

    def render_wav(self, text):
        if not isinstance(text, str):
            raise ValueError("Piper text must be a string")
        value = text.strip()
        if not value:
            return b""
        if (len(value) > 220 or any(ord(ch) < 32 and ch not in "\t\n"
                                    for ch in value)):
            raise ValueError("Piper text length or control characters invalid")
        voice = self._load_voice()
        try:
            module = self._module
            if module is None:
                import piper as module
            synthesis = module.SynthesisConfig(length_scale=180.0 / self.rate)
            output = io.BytesIO()
            with wave.open(output, "wb") as wav:
                voice.synthesize_wav(value, wav, syn_config=synthesis)
            data = output.getvalue()
            with wave.open(io.BytesIO(data), "rb") as wav:
                if (wav.getnchannels() != 1 or wav.getsampwidth() != 2
                        or wav.getframerate() != 22050
                        or not 0 < wav.getnframes() <= 22050 * 20
                        or len(data) > 1_000_000):
                    raise ValueError
            if self.volume != 1.0:
                import numpy as np
                with wave.open(io.BytesIO(data), "rb") as reader:
                    samples = reader.readframes(reader.getnframes())
                scaled = (np.frombuffer(samples, dtype="<i2").astype(np.float64)
                          * self.volume).clip(-32768, 32767).astype("<i2")
                dest = io.BytesIO()
                with wave.open(dest, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(22050)
                    wav.writeframes(scaled.tobytes())
                data = dest.getvalue()
            return data
        except Exception:
            raise RuntimeError("Piper voice synthesis failed") from None

    def speak(self, text):
        if not isinstance(text, str) or not text.strip():
            return False
        if self._sink is None:
            raise RuntimeError("Piper needs explicit audio output before speaking")
        # Take the generation BEFORE waiting for the render lock.
        # An old queued worker must not restart audio after stop().
        with self._state_lock:
            generation = self._generation
        with self._render_lock:
            with self._state_lock:
                if generation != self._generation:
                    return False
                self._cancel.clear()
                self._sink.reset()
            data = self.render_wav(text)
            with self._state_lock:
                if generation != self._generation or self._cancel.is_set():
                    return False
            return bool(self._sink.play_wav(data))

    def stop(self):
        # Revoke all queued and currently rendering generations first.
        with self._state_lock:
            self._generation += 1
            self._cancel.set()
        if self._sink is not None:
            return self._sink.stop()
        return False

    def release_for_inference(self):
        if self._voice is None:
            return False
        self._voice = None
        gc.collect()
        return True
