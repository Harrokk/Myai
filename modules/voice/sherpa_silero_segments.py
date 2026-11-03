"""Optional offline Silero VAD segmentation for MyAI 20-ms PCM16 frames.

This is a *segment* API, not a drop-in WebRTC `is_speech(frame)` replacement.
The upstream Silero model consumes 512 samples (32 ms) at 16 kHz, while
MyAI currently supplies 320 samples (20 ms). We buffer exactly and preserve
all PCM bytes until the 512-sample window is complete. No microphone or
file access occurs until the first explicit feed() call.
"""

from pathlib import Path


class SherpaSileroSegments:
    SAMPLE_RATE = 16000
    FRAME_SAMPLES = 320
    WINDOW_SAMPLES = 512
    MAX_INPUT_SECONDS = 30
    MAX_SEGMENT_SECONDS = 12

    def __init__(self, model_path="", *, vad=None, module=None, num_threads=2):
        if type(num_threads) is not int or not 1 <= num_threads <= 4:
            raise ValueError("Silero VAD threads must be 1-4")
        self.model_path = model_path
        self.num_threads = num_threads
        self._vad = vad
        self._module = module
        self._pending = bytearray()
        self._total_bytes = 0
        self._finalized = False

    def _load(self):
        if self._vad is not None:
            return self._vad
        path = self.model_path
        if not isinstance(path, str) or not path or len(path) > 512 or "\x00" in path:
            raise RuntimeError("Silero requires a verified local model")
        file = Path(path)
        if not file.is_absolute() or file.is_symlink() or not file.is_file():
            raise RuntimeError("Silero model is not available locally")
        if not 0 < file.stat().st_size <= 10_000_000:
            raise RuntimeError("Silero model size is invalid")
        try:
            api = self._module
            if api is None:
                import sherpa_onnx as api
            config = api.VadModelConfig()
            config.sample_rate = self.SAMPLE_RATE
            config.num_threads = self.num_threads
            config.provider = "cpu"
            config.silero_vad.model = str(file)
            config.silero_vad.window_size = self.WINDOW_SAMPLES
            config.silero_vad.threshold = 0.5
            config.silero_vad.min_speech_duration = 0.25
            config.silero_vad.min_silence_duration = 0.5
            config.silero_vad.max_speech_duration = 10.0
            self._vad = api.VoiceActivityDetector(
                config, buffer_size_in_seconds=self.MAX_INPUT_SECONDS
            )
        except Exception:
            raise RuntimeError("Silero VAD initialization failed") from None
        return self._vad

    def _drain(self):
        import numpy as np
        results = []
        detector = self._vad
        while not detector.empty():
            # Copy *before* pop(): upstream returns a borrowed native view.
            samples = np.asarray(detector.front.samples, dtype=np.float32).copy()
            detector.pop()
            if samples.ndim != 1 or samples.size > self.MAX_SEGMENT_SECONDS * self.SAMPLE_RATE:
                raise ValueError("Silero speech segment size invalid")
            if not np.all(np.isfinite(samples)):
                raise ValueError("Silero returned invalid audio")
            if samples.size:
                output = np.rint(np.clip(samples * 32768.0, -32768, 32767))
                results.append(output.astype("<i2").tobytes())
        return results

    def feed(self, frame):
        if self._finalized:
            raise RuntimeError("Silero session finalized; reset before new audio")
        if not isinstance(frame, (bytes, bytearray, memoryview)):
            raise TypeError("Silero input must be PCM16")
        if len(frame) != self.FRAME_SAMPLES * 2:
            raise ValueError("Silero requires exact 20-ms mono PCM16 frames")
        if self._total_bytes + len(frame) > self.MAX_INPUT_SECONDS * self.SAMPLE_RATE * 2:
            raise ValueError("Silero maximum session length exceeded")
        detector = self._load()
        self._total_bytes += len(frame)
        self._pending.extend(frame)
        import numpy as np
        while len(self._pending) >= self.WINDOW_SAMPLES * 2:
            chunk = bytes(self._pending[:self.WINDOW_SAMPLES * 2])
            del self._pending[:self.WINDOW_SAMPLES * 2]
            waveform = np.frombuffer(chunk, dtype="<i2").astype(np.float32) / 32768.0
            try:
                detector.accept_waveform(waveform)
            except Exception:
                raise RuntimeError("Silero VAD processing failed") from None
        return self._drain()

    def flush(self):
        if self._finalized:
            return []
        self._finalized = True
        if self._vad is None:
            self._pending.clear()
            return []
        if self._pending:
            import numpy as np
            chunk = bytes(self._pending)
            self._pending.clear()
            padding = b"\x00" * (self.WINDOW_SAMPLES * 2 - len(chunk))
            wave = np.frombuffer(chunk + padding, dtype="<i2").astype(np.float32) / 32768.0
            try:
                self._vad.accept_waveform(wave)
            except Exception:
                raise RuntimeError("Silero tail processing failed") from None
        try:
            self._vad.flush()
        except Exception:
            raise RuntimeError("Silero finalization failed") from None
        return self._drain()

    def reset(self):
        self._pending.clear()
        self._total_bytes = 0
        self._finalized = False
        if self._vad is not None:
            self._vad.reset()

    def is_speech_detected(self):
        return bool(self._vad is not None and self._vad.is_speech_detected())
