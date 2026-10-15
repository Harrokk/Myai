# Focused review — in-flight Voice Stop and six flagged Python calls

**Date:** 2026-10-15. **Base:** DRAFT PR #226 (commit `80478ce4484b86169fc5ed2ec3e516f8344c887a`). This review is source-only: neither a production security certification nor permission to enable real audio/native inference.

## Pass 1 — invocation / ownership / control flow

The guarded `run_tools()` boundary performs an all-tools preflight, then immediately rechecks each live tool entry at invocation. Once a Python tool callback has entered execution, a synchronous Stop signal **cannot preempt or rollback** its arbitrary side effects. Previously, a callback returning successfully after Stop could be marked `succeeded` even though the session was cancelled. The added `execution_cancelled` probe checks before invoking and immediately after a callback returns. If Stop is observed after an invocation, the attempted tool gets `state=unknown, attempted=True`, its potentially optimistic return value is replaced with fixed `EXECUTION_INTERRUPTED_MESSAGE`, and all remaining tools get `blocked, attempted=False`. All earlier verified successful tool outcomes remain visible. A known earlier completion plus an unknown outcome is `partially_completed`; an unknown with no known completion is `unknown`. No replay, retry, forced cancellation or rollback is performed.

The per-request `VoicePipeline` Stop token is supplied by `MyAICore` only in guarded voice mode. Ordinary typed `run_tools()` calls remain unchanged. A faulty Stop probe fails closed without returning exception text. There remains a small unavoidable concurrency window between the final pre-invocation probe and a callback entering native code; this cannot be made transactional merely with an Event. A native I/O operation already in flight needs its own cancellation and recovery contract.

## Pass 2 — manual classification of the six static audit flags

The audit intentionally flags calls for human review; the presence of a flag does **not** itself prove a vulnerability. This review inspected each call and its direct ownership/arguments. Flag locations correspond to the inspected base revision and may shift after other changes.

| Flag | File / original line | Review | Residual gate |
| --- | --- | --- | --- |
| 1 | `core/voice_stt_persistent.py:235` — `subprocess.Popen` | **Production, higher impact.** Worker argv derives from strict allowlisted model/audio config; launched with `sys.executable -I`, fixed checked-in worker path, `cwd="/"`, narrow offline environment, `start_new_session=True`, pipes, suppressed stderr and process-group cleanup. Not an arbitrary shell-command path. | Must test **real** native process with memory limits, helper descendants and D-state handling before activation; process-group cleanup cannot guarantee containment of helpers that escape with `setsid()`. |
| 2 | `tests/test_ventuno_whisper_base_swedish_comparison.py:202` — `exec` | **Tests only.** The test executes checked-in static `compare._METRIC_SOURCE` to exercise privacy-preserving phrase scoring; no external user prompt is interpolated by this call. No runtime network or model step is authorized in this test. | Dynamic `exec` remains a reviewable construct if the underlying static source becomes user- or file-controlled later. |
| 3 | `tests/test_voice_stt_process.py:125` — `subprocess.Popen` | **Tests only.** Synthetic one-shot child intercepts the provider's `popen`, uses controlled Python command and explicitly provided sanitized child environment to verify no inherited HF token, no stderr, isolated session/cwd. | Test must remain synthetic-only; do not replace with native model or user-selected command. |
| 4 | `tests/test_voice_stt_process.py:312` — `subprocess.Popen` | **Tests only.** Synthetic child tests CPU/address-space resource-limit environment and default-off behavior with fixed arguments. | Ensure test helper is reaped and isolation remains enforced. |
| 5 | `tests/test_voice_stt_process_group.py:30` — `subprocess.Popen` | **Tests only.** Synthetic child leader+helper probes group cleanup after leader exit; child is launched into an owned session, with bounded helper lifetime and explicit cleanup path. | Escaped process groups and kernel D-state are not covered by this test and require dedicated physical isolation work. |
| 6 | `tests/test_voice_stt_rlimit_denial.py:89` — `subprocess.Popen` | **Tests only.** Synthetic launcher passes a controlled subprocess with forced RLIMIT denial and asserts the failed worker is reaped; not an arbitrary production command entry point. | Does not validate native NPU/FasterWhisper resource usage. |

**Disposition:** All six flags have been manually **classified** at source level. The static audit will and should keep reporting these calls until its review tracking distinguishes accepted fixtures from production risk. The production `Popen` and process containment requirements are **not closed**. Do not suppress static audit warnings or claim the full project has undergone a complete independent audit.

## Regression and deployment boundaries

Tests use stub functions, synthetic utterances and disposable source checkouts; they never invoke the user's files, microphones, models, HTP/NPU, GenieX, or device-active services. Source-only ARM64 CI validates default-disabled profiles. The wider physical-presence gate remains in `docs/PHYSICAL_PRESENCE_TESTS.md`.

Review follow-up: examine whether any tool callback can expose a cooperative cancellable contract, and require post-Stop human re-verification before retrying possible partial writes. A deterministic `unknown` response is not evidence of actual failure or success.
