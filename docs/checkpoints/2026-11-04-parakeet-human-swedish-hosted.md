# Public Swedish human Parakeet trial — 2026-11-04

Stacks on DRAFT PR #388 at commit 2d306efbbddb3cfbad684441e9a21e8ce1b1d510. No merge, device access, production activation or voice-service modification.

## Independently pinned public evidence

- Human-recorded Swedish test: Google FLEURS sv_se, Hugging Face dataset commit 14b46a200cec86ab4cf963c5c0b4661ef343f34a. Full test Parquet: 537731833 bytes, SHA256 efaddda3e8460662b26d07c9fa1e52cbf57fb18365acf5bc232ea1bcf43ed935, CC-BY-4.0.
- NVIDIA Parakeet TDT 0.6B v3 INT8 sherpa-onnx export, trusted model revision 2bda32ec70b097a55adaa07d9a7173915b43cc78. Four exact immutable filename, byte count and SHA256 pins are repeated in the GitHub-hosted workflow and source script. Upstream license CC-BY-4.0.
- Exact-host ARM64-only dependencies: sherpa-onnx==1.13.8, sherpa-onnx-bin==1.13.8, numpy==2.1.3, pyarrow==20.0.0. No installation on VENTUNO.

## Source-only safety controls and measurements

- Workflow triggers only on the unique DRAFT branch and relevant paths; GitHub-hosted ubuntu-24.04-arm; fails before downloading if runner is self-hosted, non-ARM64, outside repository, or wrong branch.
- All public file downloads are from fixed HTTPS commit URLs, SHA256 and length verified before native model loading or audio decoding.
- Deterministic first twelve 1-20s bounded test samples from the human Swedish test split. No selection based on predictions. In-memory ffmpeg-to-PCM16 conversion and fixed-process isolated Parakeet from already reviewed code.
- Aggregate corpus word-edit score, empty transcriptions, latency median/p95/max, and sampled RSS for experiment Python process and descendants only. No audio or individual transcriptions in logs, no uploaded artifacts.
- WER uses word-level scoring that intentionally discards punctuation; voice authorization consensus remains the stricter punctuation-preserving comparison.
- Twelve utterances do not yield representative Swedish WER. CPU-usage and simultaneous GenieX/VENTUNO RAM are not measured. A later three-model real human comparative trial and command-negation challenge are separately required.

## Keep production blocked

risk_tiered_verification_enabled remains off; critical voice commands remain disabled. No mic, NPU, Bluetooth scanning, service restart, VENTUNO runner, private audio, human recordings from the operator, or model download on physical device.

## Results

Await exact-HEAD hosted ARM64 source-only + real-model job status, never claim success until confirmed.
