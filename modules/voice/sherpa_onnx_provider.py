"""Opt-in, CPU-only Parakeet TDT v3 STT for MyAI's existing voice pipeline.

No microphone, network, model download, audio file, or inference at import or
construction time. A caller explicitly enables voice and provides local files.
"""

import gc
from pathlib import Path


class SherpaOnnxParakeetSTT:
    """Decode one bounded 16-kHz, mono PCM16 utterance without disk writes.

    ``language='sv'`` describes the expected speech, not a forced model
    language; multilingual Parakeet TDT v3 selects its own language.
    The provider does not manufacture confidence or detected-language scores.
    """

    MODEL_FILES = (
        "encoder.int8.onnx",
        "decoder.int8.onnx",
        "joiner.int8.onnx",
        "tokens.txt",
    )
    MAX_SECONDS = 30

    def __init__(
        self,
        model_name="",
        device="auto",
        compute_type="default",
        language="sv",
        sample_rate=16000,
        channels=1,
        sample_width=2,
        num_threads=2,
        model=None,
        module=None,
    ):
        if language != "sv":
            raise ValueError("Parakeet pilot expects Swedish input")
        if device not in ("auto", "cpu") or compute_type not in ("default", "int8"):
            raise ValueError("Parakeet pilot supports CPU INT8 only")
        if (type(sample_rate) is not int or sample_rate != 16000
                or type(channels) is not int or channels != 1
                or type(sample_width) is not int or sample_width != 2):
            raise ValueError("Parakeet pilot requires 16-kHz mono PCM16")
        if type(num_threads) is not int or not 1 <= num_threads <= 4:
            raise ValueError("Parakeet thread count must be 1-4")
        self.model_name = model_name
        self.language = language
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self.num_threads = num_threads
        self._model = model
        self._module = module

    def _verified_model_files(self):
        name = self.model_name
        if not isinstance(name, str) or not name or len(name) > 512 or "\x00" in name:
            raise RuntimeError("Parakeet model requires a local absolute directory")
        root = Path(name)
        if not root.is_absolute() or not root.is_dir() or root.is_symlink():
            raise RuntimeError("Parakeet model directory is not available locally")
        result = {}
        for filename in self.MODEL_FILES:
            path = root / filename
            if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError("Parakeet model files are missing or incomplete")
            result[filename] = str(path)
        return result

    def _load_model(self):
        if self._model is not None:
            return self._model
        files = self._verified_model_files()
        try:
            module = self._module
            if module is None:
                import sherpa_onnx as module
            self._model = module.OfflineRecognizer.from_transducer(
                encoder=files["encoder.int8.onnx"],
                decoder=files["decoder.int8.onnx"],
                joiner=files["joiner.int8.onnx"],
                tokens=files["tokens.txt"],
                model_type="nemo_transducer",
                provider="cpu",
                decoding_method="greedy_search",
                sample_rate=self.sample_rate,
                feature_dim=80,
                num_threads=self.num_threads,
                debug=False,
            )
        except Exception:
            # Native model/loader errors may embed local paths and user data.
            raise RuntimeError("Parakeet model initialization failed") from None
        return self._model

    def transcribe(self, audio):
        if not isinstance(audio, (bytes, bytearray, memoryview)):
            raise TypeError("Parakeet requires in-memory PCM16 bytes")
        pcm = bytes(audio)
        if not 0 < len(pcm) <= self.MAX_SECONDS * 16000 * 2 or len(pcm) % 2:
            raise ValueError("Parakeet PCM duration or alignment is invalid")
        # No temporary WAV or audio upload; keep the waveform process-local.
        import numpy as np
        waveform = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        recognizer = self._load_model()
        try:
            stream = recognizer.create_stream()
            stream.accept_waveform(self.sample_rate, waveform)
            recognizer.decode_stream(stream)
            output = stream.result
            text = str(getattr(output, "text", "") or "").strip()
            # Parakeet v3 does not reliably expose a detected language code.
            return {"text": text, "confidence": None, "language": None}
        except Exception:
            raise RuntimeError("Parakeet recognition failed") from None

    def release_for_inference(self):
        """Drop our model reference before the resource-heavy GenieX stage."""
        if self._model is None:
            return False
        self._model = None
        gc.collect()
        return True
