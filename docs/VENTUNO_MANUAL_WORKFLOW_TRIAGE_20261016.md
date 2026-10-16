# Manual-dispatch Actions triage: 56 candidates (source-only, 2026-10-16)

**Revision:** continuation of PR #256. All **56** `workflow_dispatch`+sensitive-keyword candidates from the exact ARM64 audit inventory ([run 38943979243](https://github.com/Harrokk/Myai/actions/runs/38943979243)) were matched against the inventory, one-to-one, with no duplicates. This is a *triage of the currently checked-in job commands*, not exhaustive semantic proof, live behavior verification, or approval for any manual dispatch.

## Decision

- **15 jobs with known live model, GenieX, Ollama or QNN/HTP calls:** the **10** existing quarantines from PRs #252/#256 and **five** new board inference targets from this DRAFT. Each of the five new targeted jobs has a job-level `if: false` while an unrelated synthetic-only x86 sibling remains runnable where present. All 15 must remain disabled on the integration candidate.
- **12 metadata-only/dryrun candidates:** reviewed by source job-step summaries, not actually exercised here. A few use board-local read-only runtime metadata; names are **not** trusted as authority. Keep them off physical release allowlists pending independent full-workflow/secondary-script review.
- **27 synthetic/source-only candidates:** mostly hosted subprocess/fake STT tests and ARM64 static source checks. Source classification does not prove the test cannot access a device if called with unexpected inputs; fail closed before production signoff.
- **2 tool-staging/hosted conversion candidates:** `qairt-245-host-conversion.yml` does heavy offline x86 reference conversion; `ventuno-voice-staging.yml` downloads/installs libraries in a disposable ARM64 virtualenv. They do not become authorized production installers.
- **0 permanent execution authorizations:** every category needs an independently reviewed allowlist. Merely displaying `workflow_dispatch` or having run a similar job in a historic branch is **not** consent.

## Complete inventory (exactly 56, names retained for traceability)

### 15 disabled model/GenieX/HTP jobs

- `ventuno-diagnostics.yml`
- `ventuno-live-qairt-synthetic-once.yml`
- `ventuno-natural-swedish-stt.yml`
- `ventuno-ollama-arm64-isolated-smoke.yml`
- `ventuno-public-whisper-geniex-tts.yml`
- `ventuno-qnn-tiny-cpu-once.yml`
- `ventuno-tiny-qnn-htp-adsp-retry-once.yml`
- `ventuno-tiny-qnn-htp-once.yml`
- `ventuno-tts-isolated.yml`
- `ventuno-whisper-tiny-smoke.yml`
- `ventuno-existing-geniex-one-shot-check.yml`
- `ventuno-piper-alma-swedish-stt.yml`
- `ventuno-public-dynamic-transcript.yml`
- `ventuno-synthetic-swedish-question-stt.yml`
- `ventuno-whisper-base-swedish-comparison.yml`

### 12 metadata, inventory or dry-run workflows

- `ventuno-alsa-mixer-readonly.yml`
- `ventuno-alsa-routing-readonly.yml`
- `ventuno-capture-permissions-readonly.yml`
- `ventuno-existing-geniex-backend-reasons-readonly.yml`
- `ventuno-geniex-idle-model-readonly.yml`
- `ventuno-ollama-readiness-readonly.yml`
- `ventuno-htp-maintenance-recovery-dryrun.yml`
- `ventuno-tiny-htp-basic-profile-contract.yml`
- `ventuno-tiny-qnn-no-inference-preflight.yml`
- `ventuno-usb-audio-readonly.yml`
- `ventuno-usb-dialog-readiness-readonly.yml`
- `ventuno-v75-npu-readiness-readonly.yml`

### 27 synthetic tests or source-only controls

- `ventuno-big-hardware-test-readiness.yml`
- `ventuno-eight-sensitive-calls-review.yml`
- `ventuno-physical-voice-pilot-gate.yml`
- `ventuno-stt-bounded-stream.yml`
- `ventuno-stt-child-cleanup-failclosed.yml`
- `ventuno-stt-cleanup-reply-audit.yml`
- `ventuno-stt-concurrent-stop.yml`
- `ventuno-stt-inherited-rlimit-halfclose.yml`
- `ventuno-stt-json-startup.yml`
- `ventuno-stt-persistent-synthetic.yml`
- `ventuno-stt-pipe-resource-policy.yml`
- `ventuno-stt-process-group-descendants.yml`
- `ventuno-stt-process-hard-timeout.yml`
- `ventuno-stt-request-nonce.yml`
- `ventuno-stt-rlimit-denial.yml`
- `ventuno-stt-stop-finalize-framing.yml`
- `ventuno-usb-dialogue-controller-safety.yml`
- `ventuno-voice-cooperative-cancel.yml`
- `ventuno-voice-inflight-outcome.yml`
- `ventuno-voice-operator-reconcile.yml`
- `ventuno-voice-proc-audit.yml`
- `ventuno-voice-recovery-crash.yml`
- `ventuno-voice-retry-quarantine.yml`
- `ventuno-voice-stop-dispatch.yml`
- `ventuno-voice-stop-memory-legacy.yml`
- `ventuno-voice-write-marker.yml`
- `ventuno-voice-writer-quiescence.yml`

### 2 dependency staging or hosted CPU conversion

- `qairt-245-host-conversion.yml`
- `ventuno-voice-staging.yml`


## Verification / NO-GO

1. Verify both ten-job and five-job fail-closed scripts on the *new exact head SHA*, with synthetic tampering/unknown-job tests.
2. Inventory all tracked Actions for both candidate and `main` and veto unknown automatic trigger shapes. Regex/source scans are **not** exhaustive YAML, `uses:` or remote code provenance audits.
3. Keep effective in-memory systemd settings, production dependency consistency, real voice model inference, ALSA physical playback/recording, NPU/HTP and independent recovery **unverified**. Prior read-only production check found **0/4** usual voice dependencies.
4. New human authorization and physical operator are mandatory before running any live recording, model or accelerator; no merge to main or deployment under this triage.
