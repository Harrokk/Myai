# First operator-authorized VENTUNO metadata-only remote test — 2026-11-04

Base: DRAFT PR #393 at exact commit a2f758894db0f905ea844324ac10322ba9ac3c31.
The operator explicitly requested continuing on the accessible VENTUNO. This consent is interpreted **only** as permission for one read-only local metadata preflight, **not** microphone capture, playback, model inference, NPU, or service/deployment changes.

## Workflow gates
- Unique branch `dev/ventuno-physical-readonly-once-20261104`, one workflow path only; no manual dispatch or recurring schedule.
- First stage on disposable **GitHub-hosted ARM64**, checks exact SHA, independent structural audits, production default-OFF policy, prior sensitive-call review and synthetic fail-closed regression tests.
- Only if first stage succeeds, second stage schedules `[self-hosted, Linux, ARM64, ventuno-q]` with **strict source, architecture, nonroot `arduino` and branch guards**. Failure or offline runner is not a passed physical preflight.
- On VENTUNO, the job fetches exact commit into a fresh runner temporary directory, checks clean tracked checkout, does not modify `/home/arduino/MyAI`, never runs pip, sudo, service control, audio recording/playback, QNN, HTP, or inference, and deletes only its own temporary checkout.
- An allowlisted Python bridge runs the already reviewed metadata-only modules with deadlines and captured output: `scripts.ventuno_physical_pilot_gate --board-readonly`, `scripts.ventuno_remote_idle_baseline`, `scripts.ventuno_big_test_readiness --board-metadata-only`. Sanitized booleans and numeric idle RAM, disk and temperature are printed; raw errors, credentials, paths and audio are never exported.
- Any readiness failure yields a **NO-GO** and blocks recording. Even a green result sets physical_recording_authorized=false, physical_playback_authorized=false, critical_tool_execution_authorized=false, production_modified=false.

## Follow-up after this metadata-only board run
Review the job's exact SHA, actual runner pickup, sanitized gate results, thermal and USB state. If preflight is NO-GO, fix source-side or request a separate operator action; never auto-retry audio. If source and board metadata pass, the next action still needs fresh explicit operator consent for a single bounded real microphone/speaker experiment and a separately reviewed and authorized workflow. Three-model real STT runtime and GenieX/NPU concurrency on VENTUNO remain unknown.

**Never merge, activate voice, download models onto the board or run live audio based solely on this metadata test.**
