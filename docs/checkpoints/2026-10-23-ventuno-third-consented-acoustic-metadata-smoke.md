# MyAI – third, independently consented one-shot VENTUNO Q voice smoke

**Date:** 2026-10-23, physical run approximately 08:30–08:32 UTC (10:30–10:32 CEST).
**Disposition:** PARTIAL / STT REJECT. **NO-GO for a complete voice dialogue** and **NO repeat authorized**.

## Narrow approval, versions and runs

After the second physical smoke on 2026-10-23, the user explicitly said **"jag godkänner"** in response to a request for a further supervised single-use microphone test. This is a **third independent one-shot authorization**, not permission for background/continuous listening or automatic repetitions. User presence and whether the expected words were spoken during this particular capture have **not yet been reconfirmed** after the run.

- Fully frozen executing MyAI source: `029679ea5e10a97e867aa1db6e09bc3bcdeac3d1`, checked out detached in a restricted ephemeral runner workspace.
- Source-only synthetic Whisper diagnostic PR #359: `4171ca49d29df6a627c8bc5a3ae06c0f8ec4b29f`; final hosted CI 4323 passed, 7 skipped, plus hosted synthetic exact-worker SUCCESS. This change was **not** installed into production.
- New unique workflow-only push commit: `2747ab11c07276c2348535f1679ec1fcf6d1a80d`.
- Actual physical action: https://github.com/Harrokk/Myai/actions/runs/39925088237, job `120319384804`; `failure` from intentional exit 2 after fail-closed STT rejection.
- Concurrent full hosted ARM64 source CI at original new workflow commit: https://github.com/Harrokk/Myai/actions/runs/39925088160; **4323 passed, 7 skipped, 0 failed**.
- One-off workflow: `.github/workflows/ventuno-consented-acoustic-metadata-smoke-20261023.yml`, push path to unique branch only, matching exact commit message **and** matching expected previous SHA `4171ca49d29df6a627c8bc5a3ae06c0f8ec4b29f`, `github.run_attempt == 1`. Any later docs commit and any rerun cannot reauthorize audio. DO NOT RERUN.

## Read-only and transient checks

- Device local mock-audio safety suite: **136 passed in 3.20 s** before any live audio.
- Live readiness: `ready-for-separate-consented-dialogue-test` before staging and before playback; `ram_available_mib=13917`, `disk_available_mib=28966` at first check.
- SHA256-pinned offline Whisper Tiny CPU verification passed, as did isolated ARM64 wheel stage and temporary Swedish eSpeak.
- Actual VENTUNO eSpeak cue rendered in RAM to `cue_seconds=3.041`; bounded safe digital peak `0.039978` (less than 4% threshold), max duration 3.5 s. No claim of calibrated sound pressure level.
- One physical spoken-cue/recording step ran. `recording_attempted=true` with one **3s, 16 kHz mono S16_LE** microphone capture via `plughw:1,0`. No automatic retries.
- The limited metadata wrapper observed `capture_wall_band=3-to-3.5s`; this is the **total subprocess wall time** (including recording) and **does not separately measure the delay until ALSA became capture-ready**.
- The only recorded acoustic diagnostics are *categorical*: successive fixed one-second PCM RMS bands `0.001-to-0.005`, `0.005-to-0.02`, `0.02-to-0.08` (fractions of full-scale); `capture_activity_layout=distributed-activity`; `capture_signal_class=bounded-audio-level`. These are neither content nor an identification of a speaker, and do not prove the requested phrase was fully captured or that noise/truncation caused the failure.
- Whisper result: `status=reject-unapproved-or-unclear-test-utterance`, `unmatched_category=other-unmatched-utterance`, `transcription_verified=false`. No transcript was printed or retained. **Neither local GenieX completion nor final synthesized-response playback was attempted.**
- Post-job cleanup passed, both MyAI and GenieX services remained active. `microphone_audio_saved=false`, `microphone_audio_transmitted=false`, `transcript_logged=false`, `geniex_reply_logged=false`, `generated_wav_saved=false`, `production_changed=false`, `repeat_attempt_allowed=false`.

## Comparison and constrained next steps

First recorded attempt (Oct 22): non-silence but unrelated short utterance. Second (Oct 23 ~10:02 CEST): middle activity, other-unmatched utterance. Third (Oct 23 ~10:31 CEST): distributed activity, increasing coarse energy, other-unmatched utterance. Differences cannot prove actual content or root cause because recordings and decoded text are deliberately discarded.

Host synthetic PR #359 showed clean +800ms-shifted Piper speech accepted but artificial 12 dB/0 dB noise and 700ms-muted onset rejected by exact isolated worker. This makes **mere middle-window placement** an insufficient explanation; source/acoustics, onset loss, timing, actual spoken content, speech profile or false rejection remain unproven possibilities.

Next: obtain user report about whether the cue was heard and whether they spoke `Vad heter du?` after the pause during THIS third test; perform **source-only/offline** analysis of signal diagnostics and frozen capture path. Do not loosen the strict safe-command allowlist or log raw transcription to diagnose. Do not trigger any further microphone, physical audio, self-hosted workflow, live activation, production deployment, service restart, or main merge without renewed explicit authority and preflight.

**DRAFT checkpoint. NO-GO on end-to-end voice.**
