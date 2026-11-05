# Hosted exact decoder beam-width A/B trial — 2026-11-05

The post-loopback pinned Piper/Whisper Tiny test from PR #401 succeeded on five synthetic scenarios, but the exact harmless phrase was recognized only for the clean source and 800ms-delayed source. Synthetic 12 dB and 0 dB noise, and a muted 700ms onset, did not match the approved phrase. This is a synthetic diagnostic, not an observed property of the user's headset.

To study whether decoding beam width matters, this single-use **GitHub-hosted ARM64-only** workflow repeats exactly those five verified Piper synthetic fixtures with **unchanged beam_size=1 worker** and a disposable **beam_size=5** copy derived by a literal one-time substitution in memory. It does not modify the checked-in production worker and does not broaden the voice utterance allowlist. Only sanitized exact-question match booleans and coarse unmatched categories are emitted. Actual words, PCM and WAV never enter GitHub logs or artifacts.

The source was pinned at `492952660eb8573166b157ff024c4c7d2c7ce392`; this new DRAFT stacks on #401. No microphone, speaker, user recording, GenieX, NPU, VENTUNO physical job, production service or settings are touched. The workflow is once-only, bound to a unique branch, exact commit message, path, and run_attempt==1; uses SHA256-pinned model and voice as in #401.

A positive synthetic result alone cannot justify changing live beam settings: VENTUNO latency, RAM/CPU budget, actual speech robustness, and hallucination/false-activation behavior still require separate tests and explicit review. Critical tool dispatch and risk-tiered voice activation remain OFF.
