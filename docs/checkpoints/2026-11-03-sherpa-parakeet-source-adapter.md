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
    "vad_provider": "sherpa_silero_segments",
    "silero_model_path": "/approved/local/path/silero_vad.onnx",
    "silero_context_padding_ms": 300,
    "tts_provider": "piper_alma",
    "tts_voice_id": "/approved/local/path/sv_SE-alma-medium.onnx",
    "tts_output_device": "explicit-approved-output-device",
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

- MyAI's default VoiceActivityGate + WebRTC VAD remain unchanged.
  Explicit `voice.vad_provider='sherpa_silero_segments'` opts into a
  dedicated `SileroVoiceStreamController` wired to VoiceSession.
  Complete segments, speech-start interruption, resource handoff,
  timeout/stop reset and bounded one-utterance semantics have synthetic
  tests. This is **not** proof of safe always-on handsfree behavior.
- An opt-in `PiperAlmaTTS` provider renders the exact pinned Swedish Alma
  voice in RAM and requires an explicit sound output device before speaking.
  The physical speaker has **not** been opened or verified. The Piper
  runtime's GPL-3.0-or-later terms are separate from the Alma voice's
  CC-BY-4.0 model license; review before distribution.
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
3. **Hosted confirmed:** Silero segmenter is integrated opt-in
   with VoiceSession. Its default 300-ms synthetic silence context padding
   was selected after a successful real public Swedish word test, not by
   relaxing VAD sensitivity. Further onset/echo/noise and continuous
   microphone testing is still required.
4. **Hosted confirmed:** Swedish Piper Alma model and local synthesis
   provider verified; speaker stays closed. Actual ALSA/PipeWire audio
   routing, echo control and immediate stop are not physically verified.
5. **Wider hosted synthetic test:** 2/3 exact Parakeet+Silero recognition
   on three fixed Piper-generated Swedish questions; one phrase still
   fails. This is not a natural human speech WER or reliability estimate.
   Real-world noise, concurrent GenieX memory budget, all safety-oriented
   three-STT votes and child-process isolation remain pending.
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


## Follow-on 2026-11-03 hosted, microphone-free full speech chain

### Silero segmentation and Parakeet recognition

The first true Silero+Parakeet public Swedish fixture surfaced a
**frame-padding error**: the last 20-ms PCM frame contained literal
backslash characters instead of zero bytes, and the VAD rejected its
length. This was corrected and protected by a 640-byte frame regression.

Using the same licensed `Sv-svenska.ogg` fixture:
- [Silero + Parakeet unpadded run 41624851486](https://github.com/Harrokk/Myai/actions/runs/41624851486):
  one 1.062-s speech segment, not recognized by Parakeet in isolation,
  while unsegmented audio was recognized.
- [Context comparison run 41625244863](https://github.com/Harrokk/Myai/actions/runs/41625244863):
  adding 300 ms silence to either side of the completed segment restored
  successful word recognition.
- [Opt-in 300-ms Silero adapter run 41625803739](https://github.com/Harrokk/Myai/actions/runs/41625803739):
  **SUCCESS**; 1 segment, 1.662-s padded duration, Swedish word recognized.
  CPU model load 1.961 s, end-to-end VAD+STT on extracted speech 0.303 s,
  peak process RSS 1,234.4 MiB. Hosted ARM64 only, not VENTUNO.

### Native Swedish Piper Alma and full mocked MyAI bridge

[Hosted Piper Alma run 41624660526](https://github.com/Harrokk/Myai/actions/runs/41624660526)
**SUCCESS** using fixed public text in RAM only:
- Piper 1.8.0 pinned ARM64 wheel SHA256
  `3f60c1917de6d8e8033f395878ad3f88f6dfee88a8b05f98971a275f76a38484`.
- Alma voice SHA256
  `f75455eb6afeb1db9e2905d5bd7e4115afcd3710e0d399b6a40981766d32fedc`
  plus Swedish audio/config metadata checked.
- Generated 2.009-s mono 22,050-Hz 16-bit WAV from the fixed sentence
  `Hej. Jag heter MyAI.` with **1.266-s render time**,
  **162.6-MiB process peak RSS**.
- No speaker opened; no WAV file, user audio, or production changes.
- The new `PiperAlmaTTS` integrates with the existing TTS provider
  factory but requires an **explicitly chosen output device**, and
  does not open it during construction. Isolated native output tests
  used mock streams; physical audio playback remains unverified.

MyAI's test-only VoiceSession path now covers a complete
`Silero segment → STT → assistant response → Piper synthetic WAV
→ fake speaker sink` chain; never invokes a real microphone,
GenieX or speaker.

### Broader synthesized Swedish question test

[Hosted 3-phrase test 41626329179](https://github.com/Harrokk/Myai/actions/runs/41626329179)
**SUCCESS** (disposable hosted ARM64, same pinned three models).

| Fixed, public-text Piper synthesis | Exact recognition (whole) | Exact recognition (Silero segments) |
|---|---|---|
| Vad heter du? | yes | yes |
| Hur mycket minne använder datorn? | no | yes |
| Vad är temperaturen? | no | no |

Result: **1/3 unsegmented** and **2/3 after Silero segmentation**.
This does not imply a population accuracy rate; the phrases are
synthetic, and the remaining mismatch warrants further analysis.
Aggregate peak process RSS in the run: **1,085.5 MiB**; Parakeet
model loaded in **1.986 s**, and no user audio or speaker hardware
was used. No recognized transcripts are exported in CI logs.

### Next physical gate (not authorized yet)

1. Verify VENTUNO free RAM, disk, required Python/ALSA ABI and explicit
   microphone/speaker routing in a strictly read-only check.
2. Confirm a safe, reversible staging plan with no production service
   downtime and no unreviewed `stt_process_isolation_enabled` settings.
3. Require **new explicit consent** for any short, supervised microphone
   capture or physical speech playback; one approved test cannot
   authorize retries or handsfree mode.
4. Measure speech-start/end on real USB audio, dropouts, CPU latency,
   resource handoff to GenieX and an end-to-end Swedish reply.
5. Never auto-merge PR #374 or enable `voice.enabled`/TTS/handsfree
   on production without review and explicit approval.


## Additional 2026-11-03 Swedish speech-rate matrix and regression status

The public-text-only hosted benchmark now covers 3 fixed Swedish
sentences × 3 Piper Alma speaking rates (150/180/210), and reports
only strict-match booleans, clipped edit-distance bands and
synthetic-audio timing. It does **not** log transcripts or waveforms.

- [Rate matrix run 41627244601](https://github.com/Harrokk/Myai/actions/runs/41627244601):
  **SUCCESS**, 5/9 Silero-segment exact, 5/9 whole-waveform exact;
  baseline 180 had 2/3 segmented exact.
- [Rate matrix run 41627394052](https://github.com/Harrokk/Myai/actions/runs/41627394052):
  **SUCCESS**, 6/9 Silero-segment exact, 4/9 whole-waveform exact;
  baseline 180 had 2/3 segmented exact.
- Results vary across separate runs despite the same fixed phrases and
  pinned model versions. Do not select a supposedly optimal speed or
  claim a population WER from a small, synthesized, variable set.
  Natural human speech and noise testing remain necessary.
- [Full hosted ARM64 CI 41627394082](https://github.com/Harrokk/Myai/actions/runs/41627394082):
  **SUCCESS** with **4,487 passed / 10 skipped**;
  repository source/privacy audit PASS, no blocking findings.
- Native Silero/Parakeet integration failure now invokes opt-in
  VoiceSession shutdown and attempts to close its microphone. New
  synthetic regression cases confirm that no STT/LLM/tool action
  continues on a failed audio read and that source error messages
  are redacted. If microphone cleanup also fails, a distinct error
  is reported instead of claiming successful closure.

Important command safety: existing VoicePipeline enforces
three independent STT instances for high-risk voice commands,
regardless of the performance-oriented redundancy setting.
The Parakeet prototype does not install or certify two alternate
recognizers. A high-risk command must therefore fail closed
until a separately validated multi-model configuration exists.

**No further microphone or speaker permission has been granted by
these hosted tests.** The remaining significant boundary is a
supervised, reversible VENTUNO hardware stage, including genuine
USB capture and output routing, CPU/memory and GenieX model handoff,
and live Swedish question/reply behavior.
