# Three-family, same-human-speech hosted ARM64 experiment — 2026-11-04

Stacks on DRAFT PR #389, exact HEAD ce0f4e80727b0c313b42c4edffef97c817912fa3. Keep as separate unmerged DRAFT.

Goal: evaluate three **different provider/model families** — pinned Parakeet v3 INT8, Canary v2 Q8, Whisper Small Q5_1 — on the same 12 CC-BY-4.0 public Swedish human FLEURS utterances. Use MyAI's existing isolated workers, fully verified exact public weights and compiled-native ELF dependency checks.

- SHA-pinned FLEURS test: commit 14b46a200cec86ab4cf963c5c0b4661ef343f34a, SHA256 efaddda3e8460662b26d07c9fa1e52cbf57fb18365acf5bc232ea1bcf43ed935, 537731833 bytes.
- Parakeet upstream four-file model manifest and revision 2bda32ec70b097a55adaa07d9a7173915b43cc78: see PR #389; no repack, Python sherpa CPU.
- Canary and Whisper Small: existing independently pinned model bytes and native C++ commits in the previously audited release manifests and GitHub-hosted workflows.
- All three models are queried sequentially from exactly identical, bounded public PCM16; they never see each other's transcripts. Never start MyAI tool dispatch, risk policy, GenieX, user microphone, device services or NPU inference.
- Summaries report each model's exploratory human corpus WER (total edit/word count), median/P95/max wall time, total Python-plus-worker observed peak RSS **per sequential model**.
- An offline in-memory critical-tier transcript validator observes 12 three-family votes without creating executable receipts or running tools. Any meaningful transcript conflict remains denied; this is not real identity authentication or a production approval.
- Only aggregate counts logged; no sample text, individual audio, model weights or speech files exported.
- Synthetic source-only tests verify family identity and that WER punctuation stripping cannot relax security consensus.
- 12 samples are a small selected subset, not a statistically representative Swedish WER. Separate negative/numeric/device command evaluation and statistically reliable confidence intervals remain required. Three model families do not imply uncorrelated recognition errors. Memory does not include simultaneous GenieX, actual VENTUNO hardware or process-cgroup peaks.

Do not merge or enable risk-tier voice. All production gates remain OFF. Compare real job output at exact PR HEAD, and consider failure as a blocker, never assume success.
