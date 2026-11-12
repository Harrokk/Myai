# MyAI v2: source-only RAM/WAV comparison with official Arduino ASR Brick

**Status: DRAFT, not deployed, not operator-authorized for a live recording.**

This self-contained App Lab pilot does **not** replace
`asr_v2_official_pilot` (streaming) or any legacy MyAI voice code. It tests a
different **official Arduino SDK path** on future separately approved runs:
`ALSAMicrophone(device="plughw:1,0")` → bounded 16 kHz mono int16 audio in
RAM → in-memory WAV bytes → `WAVAutomaticSpeechRecognition(...,language="sv")`.
The mic is closed **before** ASR inference. No audio or raw transcript is
saved to disk or exported by application code. The official ASR Brick itself
may use internal service communication and diagnostics.

## Why compare?

The user-provided 12 Nov 2026 streaming logs prove:
- 125 audio packets reached ASR service, 2,048 bytes each.
- The native model detected speech but failed to complete a normal sentence
  within the eight-second stream. The service emitted speech_end at teardown.
- Native runtime printed `Non-supported or nn language detected!!!! code=nn`
  and returned empty text with result_code=2.
- `language=sv`, `translate=False` reached the service, and default VAD=700 ms
  arrived as 70 ten-millisecond frames.
- The exact native error-string source and enum mapping for `result_code=2`
  have **not** been verified. `nn` maps to Nynorsk in upstream OpenAI Whisper
  (a valid generic Whisper language), but native Qualcomm implementation may
  use its own supported-language table.

A separate VENTUNO Q developer reports successful French transcription with
Arduino `WAVAutomaticSpeechRecognition`, though on a different microphone
and app configuration. That is evidence the *API path* can work, **not** proof
the VENTUNO user's Swedish audio/model will work.

Official source reviewed: `arduino/app-bricks-py` at
`94f100ee906770e6f469f9edbc615bad895d695e`,
`src/arduino/app_bricks/asr/local_asr_wav.py` and
`src/arduino/app_bricks/asr/README.md`. The SDK accepts WAV **bytes** and
does not require saving a file.

Independent source:
https://github.com/philippe86220/VENTUNO-Q-Local-Speech-Recognition-with-Arduino-App-Lab

## Boundaries

- Maximum **eight seconds / 128,000 mono samples**, whichever is reached
  first. It captures exactly once, never retries.
- WAV is constructed via Python's `wave` module in `io.BytesIO`; only
  the generated in-RAM bytes are handed to official ASR.
- ASR decoding can continue **after** the eight seconds of microphone
  recording; this is a recording limit, not an overall execution timeout.
- Only fixed output codes, such as `reference-recognized`,
  `other-nonempty-final`, `empty-final-only`, and failure categories.
  Captured samples and words are never printed by pilot code.
- No external web requests, TTS, LLM, tool execution, production config
  change, service stop or interference with the archived legacy code.
- An explicit card index `plughw:1,0` was verified on 2026-11-06, but
  must be confirmed again before any future physical run.

**No audio is recorded by GitHub CI.** All tests use synthetic fake Arduino
APIs and PCM. User must explicitly authorize a *new* live recording after
reviewing this proposal. Do not stop MyAI or GenieX.

## Safe PCM level diagnostics (source-only extension)

The newer pilot additionally prints **one line of aggregate signal metrics**
from the WAV already held in RAM. This is neither an additional capture nor
an audio recording saved to disk:

```
MYAI_APP_LAB_WAV_V2: signal-level peak-pct=... rms-pct=... saturated-samples=...
```

- Peak and RMS percentages are relative to 16-bit full scale (32768).
- `saturated-samples` counts samples whose absolute amplitude is at least
  32760/32768. It is not a diagnosis of clipping by itself.
- The output contains no PCM bytes, speech content, words, filenames or timestamps.
- A high peak or RMS may reflect speech, noise or interference. A very low
  value may reflect mute, wrong routing or weak recording. Levels alone
  **cannot** identify which cause, or prove quality/language correctness.
- Checks WAV rate/mono/sample format and sample count before analyzing;
  failure is `signal-summary-failed`, never an unhandled raw-audio print.
- The existing one-shot maximum eight seconds and mic shutdown before ASR
  remain unchanged. No new live test is authorized by this patch.
