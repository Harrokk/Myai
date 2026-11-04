# Thirty-six human Swedish clips and paired three-family evidence — 2026-11-04

Stacks on DRAFT PR #390, exact SHA `56d4e4bd84b1f0a2bb924a47d316833117729f2a`. Keep this DRAFT, unmerged and undeployed.

The preceding 12-clip real hosted ARM64 experiment passed: Canary pooled WER 30/205 (14.63%), Parakeet 59/205 (28.78%), Whisper Small 60/205 (29.27%), with zero critical three-family transcript consensus accepted and twelve denied. Small exploratory dataset, not representative WER.

## This experiment
- Increase the same deterministic first eligible, human-recorded Google FLEURS sv_se test sample count from 12 to **36**; evaluate all three model families on exactly identical bounded PCM16.
- Keep fixed SHA256/size checked public model weights and FLEURS corpus, pinned native source revisions, direct and recursive ELF library audit, GitHub-hosted ARM64 only.
- Add aggregate paired exact transcript agreement, partitioned by exact reference-text agreement and *identical transcript that differs from the exact reference text*, and joint deviation from public reference. Add triple text-equal/reference-exact and triple text-equal/non-reference-exact counts and exact reference matches per family.
- These counts NEVER create voice receipts, approve critical commands or call tools, and never disclose audio/transcripts/speaker IDs in logs.
- Continue reporting per-family pooled word edits, wall latency median/P95/max and sampled Python+owned descendant RSS. This is **not** model memory at one standardized peak, concurrent memory, cgroup memory or VENTUNO/GenieX runtime.
- New isolated pytest contracts explicitly count non-reference-exact text agreement, never treat it as successful user authorization.

## Production safety
No user microphone, self-hosted runners, VENTUNO, GenieX, NPU, service restart, model install, native production voice factory, config changes or merge. Risk-tiered voice remains OFF and config validation rejects enablement; critical tool invocation remains denied. 36 clips are exploratory, not statistically representative or a domain-specific Swedish negation/numbers/device challenge. Model families are architecturally distinct but statistically independent recognition errors are unproven.

Exact new HEAD source-only CI and real native-model workflow results must be verified separately.

## Terminology correction (source-only follow-up)

Do NOT call identical transcripts that do not exactly match a punctuation-preserving reference "wrong" or "correct". Example: hypothesis `rapport txt` and reference `rapport.txt` have zero word edits for the existing WER scorer, yet differ in the strict authorization text comparer. Reference spelling and punctuation are not ground truth for semantic target identity. Diagnostic counters are now explicitly labeled **reference-text exactness**, and remain distinct from ordinary WER and from permission to execute tools. No prior human model inference is rerun by this diagnostic-only follow-up.
