# Unicode identifier collision hardening in STT consensus — 2026-11-04

DRAFT source-only patch based on PR #398. A review of core.voice_verification identified that NFKC Unicode compatibility normalization could turn distinct transcripts into the same candidate for a voice permission vote. Examples include superscript two versus ASCII 2, circled 1 versus ASCII 1, and fullwidth letters versus ordinary ASCII. Those differences can matter for filenames, device addresses or target identifiers.

The tiered-verification source prototype now applies Unicode NFC canonical composition instead of NFKC compatibility folding. This preserves these sensitive distinctions while still allowing canonically equivalent accent combinations and existing whitespace/casing normalization. The changed behavior affects only verification of independently attributed transcripts, not raw audio, model inference, decoding or production dispatch. Medium consensus rejects mismatched target identifiers; critical consensus rejects a different third nonempty vote.

Tests cover Unicode target collisions, third-model conflict and equivalent precomposed/decomposed Swedish accents.

Limitations: Unicode case folding still permits some textual equivalences that may be material to a case-sensitive filesystem; this is an intentionally conservative incremental improvement, not a validated typed device-ID or filesystem target parser. Critical executable voice commands remain hard-blocked at the dispatch receipt regardless of transcript majority. The risk-tier prototype remains switched OFF in production.

No physical VENTUNO job, microphone, TTS, NPU, model, service or package changes are authorized by this DRAFT.
