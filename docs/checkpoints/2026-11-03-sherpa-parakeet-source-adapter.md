# MyAI: isolated sherpa-onnx / Parakeet Swedish STT adapter

**Status 2026-11-03: DRAFT; PUBLIC SWEDISH CPU INFERENCE VERIFIED ON HOSTED ARM64. NOT INSTALLED OR RUN ON VENTUNO.**
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

- Existing MyAI VoiceActivityGate + WebRTC VAD remain unchanged.
  A separate opt-in `SherpaSileroSegments` class now supports bounded
  20-ms-to-512-sample buffering and final speech segments. It is **NOT**
  wired into VoiceSession or production VAD until end-to-end timing, onset
  and streaming interruption behavior are verified.
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
- Standard MyAI CI and unit contract tests use **only** fake recognizers.
  A separate pinned, CPU-only GitHub-hosted workflow may run the genuine
  model with a strictly licensed public fixture. No self-hosted VENTUNO
  runner, recording, persistent model installation, external user audio,
  ports, background monitoring, or service changes.
- No changes to `config/profiles/ventuno_q.json`, production
  `requirements.txt`, systemd or Arduino App Lab; no merges to main.

## Remaining gates, before any hardware use

1. **Hosted gates completed:** sherpa-onnx 1.13.8 import and CPU API
   verified on hosted ARM64. The exact upstream model archive was verified
   against the GitHub-release asset's SHA-256 before selective extraction.
   Model license reviewed: NVIDIA Parakeet TDT 0.6B v3, CC-BY-4.0.
2. **Hosted real Swedish test completed:** public Wikimedia Swedish
   one-word speech `Sv-svenska.ogg` by Peter Isotalo (CC BY-SA 3.0 /
   GFDL), SHA-1 verified. No user audio or microphone.
3. **Source-only complete:** optional Silero segment adapter and native
   VAD model verified using GitHub-hosted synthetic silence. **Remaining**
   is vetted VoiceSession integration, onset/pre-roll, interruption,
   and real (public) Swedish speech segmentation performance.
4. **Remaining:** add Piper Swedish TTS after verifying selected voice
   licensing, ARM64 inference and non-playing synthetic audio contracts.
5. **Remaining:** wider Swedish speech benchmark, realistic/noisy speech,
   concurrency and CPU peak memory with GenieX. The 1.88-second reference
   is one isolated word, not a representative WER or hands-free evaluation.
6. **Physical consent gate:** only with separately approved operator
   supervision, measure VENTUNO resource reserve, validate ALSA capture
   and run one controlled voice session with service restoration safeguards.

## Verified 2026-11-03 hosted ARM64 genuine Parakeet inference

GitHub Actions [run 41620611031](https://github.com/Harrokk/Myai/actions/runs/41620611031)
**SUCCESS** using exact source HEAD `ae3455a68c3d08ad6e6e3b7ae9b83762cb763c92`
(disposable `ubuntu-24.04-arm`; never VENTUNO).

- Official sherpa-onnx GitHub release archive:
  `sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2`.
- Exact size **487,170,055 bytes**, GitHub Release asset SHA-256
  `5793d0fd397c5778d2cf2126994d58e9d56b1be7c04d13c7a15bb1b4eafb16bf`.
- Only the four allowlisted model files were extracted to hosted scratch.
- PyAV `18.1.0` decoded the checksum-verified public Swedish OGG;
  sherpa-onnx `1.13.8` loaded and decoded it on CPU with 2 threads.
- **Actual word `svenska` recognized**, measured **model load 1.918 s**,
  **inference 0.182 s**, **public audio duration 1.881 s**,
  **peak process RSS 1,196.8 MiB**. Not VENTUNO performance.
- Prior synthetic archive/provider regressions: **29 passed**.
- No microphone, user audio, NPU, system service change or deployment.
- Project's manual-dispatch gate flagged the new test workflow's
  optional `workflow_dispatch`. This was removed (push-only) without
  weakening the gate, in commit `d45e7b26fdff96588ff82d6e47d65122c0f8e29a`.

**Current status:** real offline Swedish word recognition now verified
on a disposable hosted ARM64 CPU; production MyAI and VENTUNO remain
unchanged. This is **not** proof of live Swedish conversation on VENTUNO.


## Verified 2026-11-03 hosted ARM64 Silero VAD smoke

[Hosted synthetic Silero/Parakeet run 41621485505](https://github.com/Harrokk/Myai/actions/runs/41621485505)
**SUCCESS** on disposable ARM64, exact source
`1a21283365d497ebec84e86f1f192669275c5459`.

- `modules/voice/sherpa_silero_segments.py`: opt-in **segment** API
  (not a drop-in boolean `WebRTCVADProvider`). Buffers 20-ms PCM16
  input (320 samples) into 512-sample (32 ms) Silero windows.
- Native `sherpa_onnx.VoiceActivityDetector` receives 16 kHz
  float32 normalized samples; completed speech segments copied before
  native `pop()` and converted back to bounded PCM16, with tail
  padding and explicit reset.
- Exact public ONNX asset `silero_vad.onnx` is 643,854 bytes,
  SHA-256 `9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6`,
  verified before a short CPU native load and synthetic-silence test.
- **40 synthetic tests PASS**, native Silero CPU runtime loads and
  produces **no speech segments for 0.6 s digital silence**.
- This is **not** evidence for speech-onset sensitivity, echo handling,
  word endpoint detection or a working Ventuno microphone. No user audio,
  microphone, GenieX, output speaker or VENTUNO runner touched.
