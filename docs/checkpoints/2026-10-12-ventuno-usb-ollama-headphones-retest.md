# 2026-10-12 — VENTUNO USB → Whisper → Ollama retry with headphones

Repository: `Harrokk/Myai`
Branch: `dev/routing-boundary-followup`

## User request and safety scope

The user explained they did not wear the headphones during the
previous physical Ollama voice experiment, and explicitly asked to
**run the test again**. The user was instructed to put on headphones
before this new run and say **"Vad heter du?"** after the USB audio
cue **"Säg: Vad heter du."**

This is a **new, separately authorized, exactly once** three-second
recording and low-volume answer attempt, not a rerun of the old GitHub
workflow. The user has **not yet reported** whether the latest spoken
cue was audible to them or whether they managed to speak at the
right moment.

## New one-time authorization and run

- Source commit:
  `a8d632ade6e43055559414bfd4f519dd2d9c14d4`
- Unique workflow:
  `.github/workflows/ventuno-usb-ollama-headphones-retry-once.yml`
- Exact commit-message, branch, filepath and `github.run_attempt == 1`
  safety gates, with a separate concurrency group.
- **Actual GitHub Actions run:**
  https://github.com/Harrokk/Myai/actions/runs/38280058354
- Job: `114914902446`; overall **failure** because the fail-closed
  speech recognition acceptance criterion was not met.
- **152 / 152 mocked regression tests passed**.
- Initial VENTUNO memory **12,738 MiB** and temp disk **31,266 MiB**.
- USB capture/playback identity and access, active MyAI and GenieX
  services, current VENTUNO voice-disabled profile, pinned CPU
  Whisper model, offline Swedish eSpeak, and installed local Ollama
  all passed their preflight checks.
- The temporary local Ollama API started correctly and was confirmed
  listening on loopback.
- A one-time audio cue was issued, followed by one **3 second** USB
  recording through the authorized device. Capture succeeded.
- **NEW:** Coarse microphone level category was
  `bounded-audio-level`: no low-level or clipping diagnostic
  was triggered; this does not prove intelligible speech.
- Offline Whisper decoded the three-second PCM but the result
  was not one of the approved harmless questions or literal safe
  aliases.
- Sanitized classification:
  `status=reject-unapproved-or-unclear-test-utterance`
  and `unmatched_category=unrelated-short-utterance`.
  It was **not** the previous category
  `other-unmatched-utterance`.
- The exact decoded words are intentionally not present in CI logs
  or other persistent storage.
- `transcription_verified=false`,
  `local_geniex_answer_verified=false`,
  `playback_attempted=false`,
  `playback_completed=false`.
  Therefore, **NO Ollama chat completion was requested** and
  **NO spoken answer** was played.
- Temporary Whisper/eSpeak packages, copied source and test-local
  Ollama logs were cleaned. Local Ollama test process stopped.
  MyAI/GenieX production services remained active.

## What we can and cannot conclude

**Verified:** USB 3-second physical capture works; it contains
nontrivial PCM signal at non-clipped/non-low RMS; actual Whisper
decoding runs; safety gates correctly decline unexpected words;
installed Ollama is not the cause of this rejection.

**Not verified:** exact spoken words, whether the user heard
the latest cue, microphone orientation or speech timing, Whisper
accuracy on free-form short Swedish speech, actual Ollama chat
from recognized user voice, spoken dynamic answer, or autonomous
handsfree readiness.

Previous tests did recognize a pinned public Swedish pronunciation
fixture; that is **not** sufficient proof of reliably recognizing
the different short phrase "Vad heter du?" over the actual USB
microphone.

**Do not rerun** this audio workflow or record user speech again
without a new explicit permission. A future *synthetic-only*
diagnostic can use offline Swedish eSpeak to synthesize exactly
"Vad heter du?", pass the resulting PCM to pinned Whisper and
report only accept/reject, never raw transcription or audio.
This does not require physical audio or live user presence.
