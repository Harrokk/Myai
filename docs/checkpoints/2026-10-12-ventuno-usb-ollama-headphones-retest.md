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


## User-confirmed capture timing and synthetic Swedish Whisper accuracy probe

The user subsequently confirmed **both** hearing the prompt and
having time to speak the requested Swedish question into the
headset during the latest real three-second microphone test. This
reduces the plausibility of a simple missed-cue explanation,
but it does **not** independently prove the actual PCM contained
intelligible speech or the correct words.

Instead of recording again, a **no-audio-device synthetic control**
was created using:

- `scripts/ventuno_synthetic_swedish_question_stt.py`
- `tests/test_ventuno_synthetic_swedish_question_stt.py`
- `.github/workflows/ventuno-synthetic-swedish-question-stt.yml`

The test synthesizes **"Vad heter du?"** with temporary Swedish
eSpeak NG at two normal/slower speaking rates, converts both to
the exact **3 seconds / 16 kHz / mono / signed 16-bit PCM**
format used by the real USB capture, and passes the PCM to the
same local pinned Whisper Tiny CPU adapter. No physical
microphone, speaker, GenieX or Ollama is accessed.

### Verified result on the actual VENTUNO Q

- Source commit: `c7212369a2453eb13f12ff94a0462d9c5d413d2d`
- GitHub Actions run:
  https://github.com/Harrokk/Myai/actions/runs/38281113234
- Job: `114918351428`, **success** with all workflow steps green.
- **93/93 regression tests passed.**
- Existing public Swedish reference-word test still passed with
  the pinned Whisper Tiny model.
- The **normal-speed eSpeak** "Vad heter du?" synthesis did **not**
  produce an approved recognition:
  `normal_speed_question_matched=false`,
  category `other-unmatched-utterance`.
- The **slow-speed eSpeak** version also did **not** match:
  `slow_speed_question_matched=false`,
  category `other-unmatched-utterance`.
- This is a **successful diagnostic**, not successful speech
  transcription. The recognized words were kept private in
  ephemeral process memory, not printed or saved.
- Both active MyAI and GenieX services remained healthy; all
  temporary model, speech, voice, and checkout files were removed.

### Interpretation and next engineering recommendation

The exact test phrase failed Whisper Tiny at both synthetic
speaking rates **without** any USB microphone, ambient noise,
hardware driver or timing effects. This materially strengthens
the hypothesis that the current pinned Whisper Tiny Swedish
short-utterance accuracy is inadequate for the first voice
conversation, though it does not rule out additional real
microphone acoustic issues.

**Do not automatically repeat physical recordings or change
ALSA microphone gain.** Next compare a more capable multilingual
Whisper variant (such as Base or Small, subject to available
RAM, CPU latency and pinned-file integrity checks), and/or
bounded beam-search decoder settings against the **same**
synthetic phrase. Require successful synthetic phrase recognition
before seeking fresh authorization to record real speech.
Keep the installed local Ollama Qwen3 model and production GenieX
separate and unchanged.
