# VENTUNO Q — disposable voice dependency ABI and complete synthetic session

2026-10-16. **This is not a production installer.** Source is stacked on #242.
The physical voice pilot and exclusive HTP/NPU still require a separate
operator-approved maintenance/rollback plan.

## Full synthetic end-to-end

`tests/test_ventuno_full_synthetic_voice_end_to_end.py` uses the **real**
`VoiceSession`, `VoiceActivityGate`, `VoiceStreamController` and
`VoicePipeline` but replaces the entire microphone, VAD, STT model,
assistant/LLM and TTS with bounded fakes. It tests a complete synthetic
PCM → VAD → STT → assistant → TTS → Stop cycle and refusal/exception paths.
The test *temporarily* enables an in-memory copy of the reviewed settings
with fake providers; it does **not** change the committed OFF profile or
open a microphone. It is therefore not proof of full real-model behavior.

## Isolated VENTUNO Python ABI check

GitHub-hosted Linux downloads **only** the pinned CPython 3.12/aarch64 wheels
from `requirements-voice-arm64-hashed.lock` using `--require-hashes`
and checks the 28 exact files against
`config/voice_arm64_cp312_wheels.lock.json`. An artifact with a one-day
retention is passed to a **separate** ARM64 self-hosted job.

The VENTUNO job creates a private `mktemp -d` directory under the
Actions runner's `RUNNER_TEMP`, checks out **exact GITHUB_SHA** in that
private directory, and creates a **new venv inside that directory**.
Offline pip then installs the **28 pinned wheels from the artifact only**
into that isolated venv, without the active `/home/arduino/MyAI/.venv`.
The job checks `pip check`, then imports selected native and Python
libraries **without** calling an audio stream, TTS engine, model or
inference API.

All temporary checkout files, wheels, caches and the test venv are deleted
by a final cleanup step. Job timeout and per-process deadlines apply.
The workflow makes no changes to systemd, GenieX, QAIRT, installed models,
production settings, permanent SQLite memory, real speakers or microphones.

**A native import check cannot certify ALSA routing, device audio quality,
model accuracy, memory pressure under real inference, or GPU/NPU runtime.**
Any ABI import failure must remain NO-GO until fixed in a separate DRAFT.

## Remaining actions from audit 1–5

- Isolated end-to-end fake provider functionality: verified by the new
  targeted/full synthetic CI **only after the exact head reports success**.
- Native ABI and dependency suitability: only the disposable staging run
  can confirm this, not a successful hosted wheel download.
- In-memory runtime settings: only a *future deployed instrumented runtime*
  can provide cooperating heartbeat evidence; source-only tests are not
  retroactive proof about the active process.
- Crash recovery: signal/processgroup synthetic tests may pass while a
  physically killed native child still leaves resources; require an
  independently monitored process and cleanup confirmation before a live run.
- CI/integration: main ancestry and four quarantined historical workflows
  are source-verified. Remaining release-stage review must pin production
  deployment SHA, operator-managed rollback, and a separate authorization.

**No automatic merge, sound capture or HTP/NPU run is authorized.**
