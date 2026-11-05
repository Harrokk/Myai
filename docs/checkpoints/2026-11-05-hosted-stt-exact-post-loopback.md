# One-shot off-device exact Whisper decoder after successful manual USB loopback — 2026-11-05

The user reported hearing their own voice after a separately approved and locally run USB microphone -> USB headset loopback on VENTUNO. That verifies the audio input/output path audibly, but NOT actual Swedish speech transcription.

This DRAFT adds a one-shot **GitHub-hosted ARM64** workflow reusing the existing, previously reviewed `scripts/ventuno_exact_physical_stt_decoder_synthetic.py` and its exact physical Whisper Tiny decoding routine `_limited_whisper_child`. The inputs are **only checksum-pinned synthetic Swedish Piper speech**, including deterministic timing and noise variants. No VENTUNO runner, microphone, speaker, model installed on VENTUNO, GenieX, private recording or production config is touched.

The workflow uses a uniquely named push branch, path-only trigger on its own workflow file, a **single exact commit-message match**, `github.run_attempt == 1`, disposable hosted ARM64 Python environments, checksum validation of pinned model and voice files, and cleanup of only its isolated temporary directory. There is no `workflow_dispatch`, schedule or self-hosted runner. Never change the trigger to a reusable general voice executor.

Expected output is allowlisted coarse recognition categories from five deterministic test conditions; actual words are kept private to the ephemeral worker. A successful job demonstrates only *synthetic* compatibility with the exact physical decoder. Real microphone/STT quality and performance on Qualcomm VENTUNO remain unverified until separate limited live consent and supervised testing.

Stacked on DRAFT PR #400 and inherits the clipped-PCM fail-closed controller patch. No merge or deployment.
