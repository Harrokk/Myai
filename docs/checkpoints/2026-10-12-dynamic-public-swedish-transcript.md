# MyAI VENTUNO Q – dynamic Swedish public reference STT -> GenieX -> WAV
Date: 2026-10-12
Branch: `dev/routing-boundary-followup`

## Verified before the new test

- USB microphone: physical two-second PCM in-memory recording succeeded
  (`plughw:1,0`, 16 kHz, 64,000 bytes, nonzero RMS).
- USB speaker: Swedish eSpeak test phrase successfully streamed via ALSA,
  and the user confirmed hearing "Hej. Jag heter My AI."
- Isolated VENTUNO workflow `38251463045` showed real public Swedish
  Whisper Tiny CPU recognition as a **gate** before synthetic GenieX/TTS
  chain. The transcript itself was NOT sent to GenieX in that baseline.

## Dynamic transcript integration under test

- `scripts/ventuno_whisper_tiny_cpu_smoke.py` now makes the recognized
  **pinned, licensed public Swedish audio fixture** transcript available
  via an optional in-memory callback. The recognized text is removed
  from the subprocess result object **before** it is returned to callers
  and does not appear in workflow logs, JSON reports, files or secrets.
  Default smoke reports continue to omit recognized content.
- `scripts/ventuno_public_transcript_voice.py` validates the genuine
  transcript (bounded, reference word required, high-risk commands rejected,
  including argument-like `--`), checks memory, creates a temporary
  STT adapter returning **that** transcript to the actual
  `VoicePipeline`, and issues exactly one question through the already
  running local GenieX with the transcription incorporated into prompt
  data. The result is synthesized through the existing temporary
  Swedish eSpeak path to WAV held in memory; no physical audio I/O.
- Whisper CPU inference child must finish and release memory before
  GenieX is queried. STT model remains pinned and all STT, TTS and
  public sample artifacts are temporary; active MyAI installation,
  GenieX service, voice flags and hardware are unchanged.
- `tests/test_ventuno_public_transcript_voice.py` covers opt-in gates,
  exact real-transcript forwarding, low RAM, device-free safety,
  arbitrary/unsafe text rejection, one-call LLM gate, transcript
  suppression, and failures without leaking raw replies.
- `.github/workflows/ventuno-public-dynamic-transcript.yml`
  runs on a VENTUNO Q ARM64 self-hosted runner and reports a scrubbed
  status `myai/ventuno-public-dynamic-transcript`.

## Results and corrections during bring-up

1. Initial workflow run
   https://github.com/Harrokk/Myai/actions/runs/38252827267
   caught **two** targeted regression failures. The safety gate was
   strengthened against argument-like text and uppercase public
   reference text was accepted.
2. Next run
   https://github.com/Harrokk/Myai/actions/runs/38252964273
   confirmed **57 passed, 1 failed** before the uppercase correction.
3. With both corrections, subsequent run
   https://github.com/Harrokk/Myai/actions/runs/38252969742
   confirmed **58 targeted tests passed**, all ARM64 STT wheels could
   be isolated, and the SHA1-pinned public speech fixture loaded.
   The integration step **did not run** because the workflow invoked
   the previous hardcoded-fixture module name with the new CLI flag.
   No physical audio or production service changes occurred.
4. Workflow launch target fixed in commit
   `48e1e2d87e17304caa1c6d9616ecc2e7bd5b6660` to execute
   `scripts.ventuno_public_transcript_voice`.
   **The full corrected run is pending verification here.**
   Do not mark real dynamic transcript -> GenieX -> WAV as passed
   without its final run log.

## Critical boundaries

This integration uses the **public Swedish reference word**, not the
user's USB microphone, and neither listens nor speaks physically.
It does pass a real recognized transcript to the real local GenieX
model via MyAI's actual voice pipeline; success would validate this
one reference phrase only. It does not prove free-form questions,
turn-taking, wake-word/VAD, echo handling, long-running sessions or
production readiness. Further live audio tests require fresh
authorization and incremental verification.
