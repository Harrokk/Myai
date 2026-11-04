# Source-only diagnostic label correction — 2026-11-04

Base: DRAFT PR #391 exact commit `4b3ead27071358e17f3300e3e3861247fd9ca813`. This change does not alter any runtime voice model, consensus verifier, tool authorization, trusted weights, audio or hardware.

Verified prior same-human-audio hosted ARM64 [36-clip run #41800129243](https://github.com/Harrokk/Myai/actions/runs/41800129243): **SUCCESS**, 36 public Swedish FLEURS utterances and three independent model families, critical text verifier **0/36 accepted**, no tools executed. WER Canary 82/668, Parakeet 155/668, Whisper Small 168/668; these exploratory results remain valid.

**Issue corrected:** experimental diagnostics used terms `same_wrong_agreement`, `three_same_wrong` and `correct_exact_agreement`. The comparison actually uses the punctuation-preserving `_canonical()`: hypothesis "rapport txt" versus reference "rapport.txt" differs in exact text despite having **zero word edits**. Therefore those names overstated semantic correctness/incorrectness.

- Rename only aggregate diagnostic counters to **agreement_exact_reference_text**, **agreement_nonexact_reference_text**, **both_nonexact_reference_text**, **three_same_exact_reference_text** and **three_same_nonexact_reference_text**.
- Add source-only tests demonstrating punctuation-only exact-text divergence is not evidence of a misunderstanding, while missing negation is not equated with the reference.
- Retain all existing 1/2/3 votes, fail-closed strict punctuation-preserving text consensus, separate critical approval unimplemented, default OFF, and explicit config rejection.
- No new claims of representative Swedish accuracy, domain-specific command safety, statistical independence or concurrent on-device memory.
- Only source-only GitHub-hosted ARM64 CI is needed to verify label/test changes. The 36-clip model-backed comparison at the previous exact HEAD is referenced as historical evidence, **not** claimed to have rerun on the new commit.

NO MERGE, NO DEVICE/VENTUNO OR GENIEX CHANGES, NO PRODUCTION ACTIVATION.
