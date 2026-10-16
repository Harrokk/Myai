# VENTUNO remote phases 1–5: operator and release checklist

The new source-only ledger `python -B -m scripts.ventuno_remote_phases_1to5`
reports exactly what can be asserted **without installing or running voice**.

| Phase | Evidence already present | Remaining hard stop |
|---|---|---|
| 1. ARM64 voice dependencies | 28 exact wheel hashes, hosted-only resolution | Install into a disposable *board-local* venv outside production, verify native library imports, sounddevice/PortAudio/eSpeak compatibility and cleanup; do not mutate installed venv |
| 2. Synthetic end-to-end voice | Existing synthetic PCM/STT/voice-pipeline tests and process isolation | Execute complete staged STT→LLM→TTS with dummy providers and explicit memory/exit/resource assertions in disposable environment |
| 3. Effective settings / crash isolation | Future in-process heartbeat flags, isolated trial DB, write-ahead recovery modules | Demonstrate actual running process settings and crash/rollback on the exact staged release; no assertion based solely on a disk config |
| 4. CI quarantine | Four main-only workflows inert in integration candidate | Manually review all release-triggered workflows, action permissions, and self-hosted access before any merge |
| 5. Release candidate | Real main ancestry in DRAFT, SHA-pinned wheel lock and green source CI | Final code diff, version/rollback snapshot, separate authorized deployment and observed health checks |

**Decision:** source-only green is not a go-ahead for microphone, speaker, real model or NPU. Stop if the disposable environment cannot be guaranteed isolated from `/home/arduino/MyAI`. No automated deployment, package install, service restart or hardware execution is authorized.
