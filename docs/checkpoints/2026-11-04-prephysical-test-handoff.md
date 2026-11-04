# MyAI — handoff at the first physical VENTUNO test (2026-11-04)

**Status boundary:** GitHub-hosted SOURCE REVIEW permits requesting a **separately authorized, read-only physical-board preflight**. It does NOT approve microphone, speaker, NPU, live model, reconfiguration, service restart, merge, or any effectful voice tools.

**Repo:** Harrokk/Myai. The current DRAFT stack is PR #375→#384, #386→#391 (PR #385 is a separate experiment and must not be accidentally merged as part of #386). This handoff DRAFT must be based on PR #391's exact tested HEAD. Record new commit SHA and both CI run URLs before physical use.

## Completed before board interaction

1. Pinned hosted ARM64 native Canary 1B v2 Q8, Whisper Small Q5_1, and sherpa-onnx Parakeet 0.6B v3 INT8 model inference, with exact public FLEURS sv_se human speech test corpus hash.
2. Twelve-clip real-human comparison successful. Thirty-six-clip run #41800129243 successful: same 36 clips and 668 reference words; WER Canary 82/668 (12.28%), Parakeet 155/668 (23.20%), Whisper Small 168/668 (25.15%). Strict punctuation-preserving non-executing critical consensus: zero accepted, 36 denied. **These are exploratory research figures, not safety acceptance criteria.**
3. HMAC now includes the Boolean tool argument-delivery policy. Different filenames, decimals, device IDs and punctuation no longer silently collapse in tiered voice consensus. Existing separate approval requirement for critical actions is untouched.
4. The latest PR #391 addition separates WER-like word agreement diagnostics from **authorization**; neither word agreement nor aggregate error metrics can issue a tool permit.
5. GitHub-hosted full source suite, static privacy audit and local mock security tests must pass at **exact handoff HEAD**. This handoff adds an independent two-pass structural source audit, sensitive-call AST review, a source-only physical preflight gate, and negative cases that deny unsafe flags.
6. Audits are automated structural passes, **not proof of a human line-by-line manual inspection of every tracked file**. The source-only CI originally flagged 15 sensitive sites for manual attention. The eight previously flagged AST sites are checked by `scripts.ventuno_eight_sensitive_calls_review`; audio-push workflow flags are **inert due to `if: false`** at their device jobs. `core/selfdev_bounded_runner.py` and `core/voice_candidate_native.py` have bounded, dedicated-process-group wrappers but still merit on-device observation during a future approved pilot. The 15 flags are not evidence of 15 active vulnerabilities.

## Exact first physical test — order (DO NOT RUN REMOTELY NOW)

Only when the operator is physically present and explicitly requests test phase A:

A. **Power and emergency stop.** Have physical access to USB and power; confirm the board has stable power, thermal headroom, cooling, and a way to stop audio/processes immediately. Keep all production MyAI and GenieX services in their present state. Preserve configuration, runner registration, existing memory.db and all user files.
B. **Freeze Git SHA.** Use one new temporary checkout of the exact GitHub-hosted-tested handoff SHA outside `/home/arduino/MyAI`, under a private per-job scratch directory. No source copy or installation into production; verify `git rev-parse HEAD`, clean tracked worktree, and SHA match. Do not use a floating `main` or earlier branch name to justify execution.
C. **Read-only system and safety metadata.** Confirm hardware architecture `aarch64`, nonroot user `arduino`, runner/service health, GenieX status, USB microphone/headset identity *and re-enumeration*, ALSA capture/playback access, physical temperature, free RAM (8-GiB reserve required by existing board voice gate), disk reserve, process count, network status and whether audio/model processes are already running. No capture, playback or model execution in this step.
D. **Existing bounded board read-only gate**, from the pinned scratch checkout only: `python3 -B -m scripts.ventuno_physical_pilot_gate --source-root . --expected-sha <FULL_PINNED_HEAD_SHA> --board-readonly`. On the board use the already verified local venv Python path if required by the gate's documented dependencies; never pip install just to pass it. Require `status=board-readonly-preflight-passed` and `ready_for_separate_human_consent=true`. Note that this *still is not consent*.
E. **Independent read-only hardware matrix**, using `scripts.ventuno_big_test_readiness --board-metadata-only` in the same staged source. Expected status is `metadata-completed-needs-operator-test`, not "NPU passed." Any other status or contradictory report blocks progress.
F. **Record sanitized outcomes only**: exact SHA, command status category, USB device existence / access booleans, CPU/RAM/disk/temp category, source and active profile OFF booleans, service state, and whether human consent is needed. Never log secrets, audio, raw transcripts, private paths, Wi-Fi identifiers or credentials.
G. If A–F are all accepted and the operator separately authorizes an individual audio experiment, **plan a new, explicit one-shot physical audio test**: one benign prerecorded/control phrase with microphone consent, capture duration bound and cleanup, stop button, service checks and audio deletion. One-shot recording must never be triggered merely because the read-only gate passes. Avoid critical commands, GPIO/relay, Bluetooth pair/auto-connect, workspace writes, selfdev, firmware/NPU updates or wake-word always-on. Do not reuse old recorded consent.

**STOP / NO-GO immediately:** USB microphone/headset disappeared or re-enumerated; source or active profile is not OFF; SHA mismatch or dirty code; runner UID not expected; GenieX/service unhealthy; free RAM/disk below gate reserve; overheating, OOM, power instability; unknown package/model provenance; observed audio or NPU use during metadata phase; unexpected privilege escalation; board confirmation unclear. Leave production unchanged and save a privacy-sanitized checkpoint.

## Unresolved beyond the initial physical preflight

- Tiered 1/2/3 STT is still **NOT** wired to the trusted production voice factory. `voice.risk_tiered_verification_enabled` remains OFF and the config validator rejects turning it on.
- Critical effectful voice commands have NO separately authenticated human-approval integration; they remain hard-blocked even if all three transcripts agree.
- Whisper, Canary and Parakeet performance **on the VENTUNO** with concurrent GenieX/NPU, cgroup memory, CPU thermal throttling, USB audio route and real low-latency response is unmeasured. Hosted process-tree RSS is not a VENTUNO capacity guarantee.
- Representative Swedish accuracy, negations, numerical/decimal, Bluetooth ID and filename intent safety, noisy multi-speaker audio and test-retest independence need dedicated verified challenge data.
- Direct HTP/NPU operator execution/placement and safe off-device rollback have not been verified; metadata-only gates cannot authorize firmware or NPU maintenance.
- Dependency locks for the entire app are incomplete: `requirements.txt` has version ranges and the optional sherpa wheel file is not an audited, complete hash-locked wheelhouse for the physical board.
- No production merge, rollout, voice enablement, or unattended hardware test is authorized by this checkpoint.

## Handoff decision

**Source-only GO:** request physical test phase A–F with the operator physically present, **only after exact HEAD hosted audits and tests pass**.

**Physical voice GO:** NOT YET. A–F plus new explicit one-shot operator consent are prerequisites.

**Critical/risk-tiered production voice GO:** NO-GO until independent provenance, critical external identity/approval, authentic Swedish challenge, concurrency memory and on-device runtime evidence are separately passed.
