# Voice consensus and attestation hardening — 2026-11-04

Base: DRAFT PR #387, exact SHA `61d47253fdfad2725ecafc888130fae7116b557e`. This is a separate stacked DRAFT. Do not merge or deploy until reviewed.

## Confirmed source-level issues and patch
1. `sign_voice_plan` previously omitted the tool's `pass_user_input` policy from its HMAC. Sign the exact Boolean policy, fail closed on non-Booleans, and revalidate at dispatch.
2. `_canonical` previously stripped punctuation from STT results. This could collapse a filename, decimal, device identifier or path into a distinct instruction. Preserve punctuation and normalize only Unicode NFKC, case, and whitespace. This is intentionally stricter: two speakers' transcripts with different punctuation now **fail closed** until a validated typed-target comparator exists.
3. Do **not** lower the conservative `stäng av Bluetooth` critical classification. Add a regression test preserving critical status; review typed, reversible Bluetooth semantics separately.
4. The synthetic real-model Swedish speech smoke currently reports word edits without a quality pass threshold. Keep it clearly labeled functional smoke, not an accuracy gate. A separate representative Swedish corpus and critical-command challenge is required.

## Tests
- Signed `pass_user_input` mutation and non-Boolean values fail.
- Permit issued before argument-delivery policy mutation is unusable.
- Independent STT votes disagree on punctuation relevant to Bluetooth IDs, file paths, decimal values and filenames.
- Critical two-identical-one-conflicting punctuation voter remains denied.
- Case and whitespace alone remain tolerated; Bluetooth shutdown stays critical.

## Non-activation and missing evidence
- `voice.risk_tiered_verification_enabled` remains default false; config validation still rejects true.
- No updates to production voice factory, native STT models, dependencies, runner services, VENTUNO, microphone, NPU, or GenieX.
- No WER, real Parakeet inference, total concurrent cgroup RSS, three-family hosted verdict or on-device runtime benchmark.
- Requires exact HEAD GitHub-hosted ARM64 full test suite and independent two-pass review; never treat unit tests as proof of production readiness.
