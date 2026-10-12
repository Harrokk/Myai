# VENTUNO Q – first consented USB mic -> Whisper -> Ollama -> Swedish TTS

Date: 2026-10-12
Repository: Harrokk/Myai
Branch: `dev/routing-boundary-followup`

## Authorization and scope

The user explicitly approved proceeding with the previously identified
**physical** USB microphone -> Whisper STT -> installed Ollama -> offline
Swedish eSpeak -> USB speaker experiment ("Ok kör").

Exactly **one** three-second microphone capture and **one** low-level
speaker response are allowed per unique one-shot authorization. VENTUNO
first plays the fixed, 4%-peak-limited spoken instruction
"Säg: Vad heter du." before opening the microphone. The user was
told to answer "Vad heter du?" when the cue plays.

This authorization does **not** permit recurring capture, handsfree
mode, voice-enabled production changes, a second attempt, or a
systemd/GenieX restart.

## Verified prerequisites from preceding workflows

- USB card 1 device 0 supports accessible capture and playback.
- Physical microphone input earlier captured a nonzero PCM waveform.
- User personally confirmed audibly hearing Swedish TTS from USB speaker.
- Pinned ARM64 CPU Whisper Tiny recognized a public Swedish word, and
  had previously forwarded its real public transcript through GenieX.
- Official Ollama ARM64 v0.34.0 and model qwen3:0.6b were persisted at
  `/home/arduino/.local/opt/myai-ollama/v0.34.0`, without a permanent
  server or production config switch.
- Actual `core.ollama_client.OllamaClient` through the MyAI local
  LLM provider factory already generated a real bounded Swedish
  text reply (run `38267233100`).
- The synthetic USB audio controller and newly selectable backend
  passed 117 tests (run `38266474560`).

## New exact one-time consent workflow

- `.github/workflows/ventuno-usb-ollama-voice-consent-once.yml`
- Source authorization commit
  `c35e54143b720bd46f913d01575627ca1afd24df`
- Only triggers on a push touching that workflow path with exact
  authorization commit title and `github.run_attempt==1`.
- Checks VENTUNO platform, active MyAI/GenieX services, USB ALSA
  card 1:0, 8 GiB free-RAM gate, staging disk headroom, model
  integrity and pinned public Swedish Whisper fixture.
- Uses temporary ARM64 Whisper and Swedish offline eSpeak staging,
  not production service/package installation.
- Uses the **already installed** Ollama model via loopback-only
  `127.0.0.1:11434`; starts it only around the one-shot physical
  test and stops it in a trap.
- Explicitly passes `response_backend="ollama"` to the USB audio
  hardware adapter. GenieX is not used to answer the test question.
- Only allows narrowly accepted innocuous Swedish utterances,
  including a handful of safe normalized name-prefixed aliases.
  Failed recognition is recorded only by a bounded failure category,
  not by raw transcript.
- PCM, transcript, model answer, WAV and temporary model caches are
  never persisted to project files or CI logs. Response WAV is capped
  to 4% digital peak and checked again before physical speaker access.
- After the test, source checkout, Whisper staging, eSpeak staging
  and transient Ollama logs are cleaned. Production GenieX/MyAI
  are verified active and production voice flags remain disabled.

## Current verification boundary

**Workflow source is created, final self-hosted GitHub run result has
not yet been verified in this checkpoint.** Do not infer physical
capture, successful transcription, spoken response, or audible speaker
sound until the exact GitHub run's steps and sanitized log are
inspected. If the one-shot job fails, do NOT rerun the audio
without new user permission.


## Verified outcome of first one-shot Ollama spoken test

The single user-approved physical test completed on the actual
self-hosted VENTUNO Q ARM64 runner:

- Exact one-shot authorization commit
  `c35e54143b720bd46f913d01575627ca1afd24df`
- GitHub Actions run:
  https://github.com/Harrokk/Myai/actions/runs/38272896093
- Job `114891244168`, overall **failure** due to an
  intentionally fail-closed speech matching result, not due to
  a missing Ollama installation.
- **150/150 synthetic safety regression tests passed**.
- Initial available RAM **12,745 MiB**, free disk **31,267 MiB**.
  Both services and USB card 1:0 accessible.
- Pinned public Swedish reference passed Whisper CPU preflight;
  temporary eSpeak Swedish synthesis passed; USB/resource final
  preflight passed.
- Installed Ollama started and responded to its loopback
  `/api/version` readiness request before the one-shot audio step.
- The fixed cue was delivered by the driver before one **3-second**
  physical USB microphone recording. The recorded PCM passed the
  controller's non-silence gate, but Whisper's decoded text was
  **NOT** an approved short question.
- Sanitized result:
  `status=reject-unapproved-or-unclear-test-utterance`,
  `unmatched_category=other-unmatched-utterance`,
  `recording_attempted=true`,
  `transcription_verified=false`,
  `playback_attempted=false`,
  `playback_completed=false`.
- **No Ollama chat call** and **no spoken answer playback** occurred.
  The original transcript, raw audio and generated model content
  were neither printed nor stored, so the true cause cannot be
  established from logs. A cue timing, low microphone gain,
  environment sound or Whisper interpretation problem are all
  hypotheses, **not confirmed causes**.
- The Ollama server process was stopped by the shell trap,
  temporary model/voice and runner directory removed, both
  production MyAI and GenieX services verified active.
- GitHub's one-time audio authorization does not apply to any
  later run and **must not be retried** without new explicit user
  permission for another physical recording.

### Software-only privacy-safe follow-up

The voice controller now optionally emits a coarse **signal quality
category** derived from only the ephemeral 96,000-byte signed PCM:
invalid, silence/too quiet, low microphone level, bounded range,
very loud, or possible clipping. This never emits sample data,
transcripts or waveform timing. It was added *after* the real audio
attempt in commits `bddd2b32fb8004e00bf62a52762fc93cb42ff9e6`
and `a29b357cccd31d699e3abc700b921c9437bc2192`.
The historical physical run did **not** include this metric.
It will only become useful on a **new explicitly authorized** test.

Next user-level question: did the user hear the spoken cue and say
"Vad heter du?" during the three-second window? Do not attribute
the mismatch to missing user speech without confirmation.
