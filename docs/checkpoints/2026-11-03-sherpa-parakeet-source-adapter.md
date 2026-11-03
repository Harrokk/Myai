# MyAI: isolated sherpa-onnx / Parakeet Swedish STT adapter

**Status 2026-11-03: SOURCE-ONLY DRAFT. NOT INSTALLED OR RUN ON VENTUNO.**
Stacks on MyAI DRAFT PR #373 at `e691e57a9f9fa059cf656a5603828472ef0b4c9e`.
The original Arduino App Lab pilot is left in place, unchanged.

## Rationale

The real VENTUNO microphone supplied PCM to the Arduino ASR engine on
2026-11-03, but native Whisper returned `mEverDetectedSpeech=0`. Rather
than mutate live ALSA, model, GenieX or VAD thresholds, prepare an alternative
well-supported speech recognizer behind MyAI's existing STT provider interface.

Upstream references:
- sherpa-onnx: https://github.com/k2-fsa/sherpa-onnx (Apache-2.0).
- Parakeet TDT 0.6B v3 INT8: https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html
- Python API: https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/python/sherpa_onnx/offline_recognizer.py
- The model supports 25 European languages including Swedish. The model's
  published license is CC-BY-4.0; review model provenance and attribution
  separately before redistribution.

## What is implemented

- `modules/voice/sherpa_onnx_provider.py` exposes
  `SherpaOnnxParakeetSTT.transcribe(pcm_bytes)` and
  `release_for_inference()`, matching the existing MyAI STT return shape.
- `core/voice_factory.py` registers optional key `sherpa_onnx_parakeet`.
  **Existing default remains `faster_whisper`**; disabled voice produces
  no provider and no hardware access.
- Input contract: at most 30 seconds of 16-kHz, mono, little-endian
  signed PCM16 bytes; no WAV scratch files, no HTTP, no model download.
- The provider only loads a local four-file Parakeet INT8 transducer
  directory on the first explicit transcription call; it uses
  `OfflineRecognizer.from_transducer(..., model_type='nemo_transducer', provider='cpu')`.
- Unsupported device / sample formats and missing or symlinked model files
  fail closed. Native loader/decoder exceptions are redacted.
- Optional native Python dependencies are pinned **only** in
  `requirements-sherpa-voice.txt`, not production requirements.
- Synthetic tests cover PCM normalization, local model-file contract,
  no eager model load, errors and cleanup, opt-in factory wiring, and
  continued rejection of unreviewed isolated-worker combinations.

## Example configuration (illustrative only; DO NOT APPLY TO VENTUNO)

The model name must be the **existing absolute directory** holding
`encoder.int8.onnx`, `decoder.int8.onnx`, `joiner.int8.onnx`,
and `tokens.txt`. The model is NOT shipped in Git or installed automatically.

```json
{
  "voice": {
    "enabled": false,
    "tts_enabled": false,
    "handsfree_enabled": false,
    "stt_provider": "sherpa_onnx_parakeet",
    "stt_model": "/approved/local/path/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8",
    "stt_device": "cpu",
    "stt_compute_type": "int8",
    "stt_language": "sv",
    "backup_stt_provider": "faster_whisper",
    "backup_stt_models": []
  }
}
```

The multilingual Parakeet model selects language internally; setting
`stt_language='sv'` is a contract constraint for this pilot, **not proof
of hard-locking Swedish recognition**. The adapter returns
`confidence=None`, `language=None` unless a later verified model
interface provides a trustworthy detected-language value. Never interpret
the configured expected language as a recognized language confidence.

## Explicit limitations / no-go

- Existing MyAI VoiceActivityGate + WebRTC VAD remain unchanged; **Silero VAD
  has not been integrated**. A Silero adapter requires frame-size,
  endpoint and buffering tests before replacing the 20-ms frame provider.
- Piper Swedish TTS is a separate future opt-in component; **no Piper
  provider was installed or connected in this commit**.
- The Parakeet INT8 model is approximately 640 MB extracted. Its RAM peak,
  CPU-only latency on QCS8275, concurrent GenieX behavior, and actual
  Swedish recognition quality on VENTUNO are **unverified**.
- Existing process isolation currently supports built-in FasterWhisper
  only. An attempt to enable it with this new provider is rejected by
  the existing factory safety gate. Model reference release does not
  guarantee native allocator memory return.
- The existing three-STT/vote/command-confirmation rules have not been
  changed or independently revalidated with this model.
- GitHub-hosted synthetic CI must use **only** fake recognizers; no
  self-hosted VENTUNO runner, recording, model loading or external model
  downloads. No continuous listener, new ports, background monitoring
  or service changes.
- No changes to `config/profiles/ventuno_q.json`, production
  `requirements.txt`, systemd or Arduino App Lab; no merges to main.

## Remaining gates, before any hardware use

1. Review model artifact SHA-256, licensing, local cache ownership and
   suitable CPU-only aarch64 wheels (including CPython ABI) in a disposable
   hosted or local staging environment. Do not run a model downloader
   inside production MyAI.
2. Run **actual** sherpa-onnx inference using a licensed, public Swedish
   audio fixture in a disposable hosted ARM64 environment; measure
   accuracy, memory peak and elapsed time. No user microphone audio.
3. Separately design and test the Silero VAD frame adapter using only
   synthetic audio and upstream documented APIs.
4. Add an opt-in Piper TTS adapter after its Swedish voice/model license
   and ARM64 performance are verified. No automatic audio playback.
5. Only with a new explicit, physically supervised authorization:
   check VENTUNO CPU memory reserve, ALSA permissions and single-use
   voice capture; preserve GenieX/MyAI service restoration safeguards.

**Current status:** first source-only swappable provider is prepared;
no claim of complete spoken-dialogue operation or successful hardware
integration is made.
