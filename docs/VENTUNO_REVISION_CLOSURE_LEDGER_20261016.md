# MyAI revision closure ledger — 2026-10-16

**Scope:** source-only DRAFT continuation of the two-pass audit from PR #238. This file is a conservative status register, **not** a release approval. It follows staged PRs #240, #242, #247, #248 and #249 and accompanies the deep-audit CI fail-closed correction. No production service was changed, and no microphone, speaker, model inference, HTP or NPU was exercised here.

## Status of original 12 audit findings

| Audit item | Remote evidence | Closure status / mandatory next gate |
| --- | --- | --- |
| 1 — Installed voice libraries / ARM64 ABI | 28 SHA-256-pinned ARM64 wheels; disposable board-local install, seven imports with temporary distro PortAudio/JACK; synthetic eSpeak in-memory WAV verified in #247 | **PARTIAL**: installed production interpreter/runtime and actual STT/audio stream still unverified |
| 2 — Main/DRAFT divergence | Two-parent source-history integration candidate in #240 plus subsequent stacked DRAFTs | **PARTIAL**: final branch diff, full checks on final release SHA and approved merge absent |
| 3 — Whisper Small isolation / memory | Disabled isolated voice profile and synthetic process/model tests | **OPEN**: actual Whisper Small decoder, resource limits, responsiveness and shutdown in a chosen runtime |
| 4 — Private WAV cleanup | Error-injection cleanup correction and synthetic tests in #238 | **PARTIAL**: process death/power loss and disk persistence not demonstrated safe |
| 5 — Effective active settings | Future in-process limited heartbeat/attestation code | **OPEN**: no evidence the installed running service is the reviewed source/config |
| 6 — Test memory separation | Disabled voice trial config with separate SQLite path, no-write source assertions | **PARTIAL**: live trial separation and WAL/cleanup require separate approved test |
| 7 — NPU/HTP QAIRT compatibility | Source inspection and passive preflight only | **NO-GO** until model/driver/QAIRT/operator tool compatibility and human-controlled physical recovery |
| 8 — Process descendants/recovery | Synthetic group cleanup and conservative process census; out-of-band stop contract | **OPEN**: actual native descendant tree/independent recovery after failure |
| 9 — Dependency lock/reproducibility | Voice-specific 28-wheel hash lock; PyAV 18.1.0 compatibility and isolated imports | **PARTIAL**: whole-runtime dependency manifest and reproducible installed release image not proven |
| 10 — Legacy workflows | Four main-only workflows quarantined on integration candidate; static inventory of other Actions workflows | **PARTIAL**: final human review of all triggers, permissions and effectful dispatch paths before merging |
| 11 — Physical USB audio / latency | Synthetic real MyAI pipeline to eSpeak WAV; earlier independent ALSA one-shot | **OPEN**: permitted full mic→STT→assistant→speaker and Stop, p50/p95 latency/temperature |
| 12 — Remaining modules | Static tool registry and unit tests in source | **OPEN**: per-module dependency, import, device/security and end-to-end verification |

**Manual review completeness:** both automatic full tracked-source passes were performed; select high-risk code paths were manually inspected. This is **not** proof of manual line-by-line review of every file, functional coverage, or deployed behavior. That distinction remains an independent review requirement.

## Verified evidence (do not substitute between commits)

- PR #247 isolated native voice package import, PortAudio and Swedish synthetic eSpeak stage: successful disposable ARM64 run [38927510336](https://github.com/Harrokk/Myai/actions/runs/38927510336). No production installation or live audio.
- PR #248 head `da8591804b6b2d0f318fee3cfc53086b395b155b`: full [ARM64 CI 38930516544](https://github.com/Harrokk/Myai/actions/runs/38930516544) **3144 passed, 15 skipped**. Its independent hosted-only workflow [38930518427](https://github.com/Harrokk/Myai/actions/runs/38930518427) had **startup_failure**, not a pass.
- PR #249 head `38fcd6ca797b23eab6437d1864990bfa7c963c2e`: full [ARM64 CI 38932265781](https://github.com/Harrokk/Myai/actions/runs/38932265781) **3147 passed, 15 skipped** and source/privacy audit passed on that exact SHA.
- This new DRAFT head **must obtain its own** syntactic, test and deep-audit check; results from earlier commits are not transferable.

## Release blockers and stop conditions

- **No deployment/main merge** on this evidence. A new final integration/release candidate must be checked and explicitly reviewed first.
- The deep audit CLI must exit nonzero for `source-audit-with-findings`, incomplete scan, missing/malformed evidence, or any automatic blocker. A shell exit of 0 is valid only for `source-audit-completed` and an empty blockers list; it **still does not authorize deployment**.
- The current installed configuration, live STT memory/latency, audio routing, actual package environment, crash/rollback and native process cleanup need separately witnessed verification.
- No active audio recording/playback without specific fresh operator approval. No GenieX/NPU/HTP inference without separately agreed physical test, compatibility proof and independent recovery.
- Disconnected or skipped CI, unreviewed hardware-capable workflows, or unknown runtime writer state always mean **NO-GO**.

**Next safest remote step:** complete exact-SHA source-only audit and regression; scrutinize remaining workflow triggers and deployment diff. **Next physical step (separate approval):** operator-supervised limited voice trial and stop/recovery, followed only later by NPU maintenance.
