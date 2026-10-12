# VENTUNO Q – privacy-preserving closeness diagnostics for Swedish ASR

Date: 2026-10-12
Repo: Harrokk/Myai
Branch: dev/routing-boundary-followup

## Reason for test

Previously verified VENTUNO runs show **0/8** exact matches of
"Vad heter du?" when two synthetically generated Swedish utterances
are recognized using Whisper Tiny and Whisper Base with beam sizes
1 and 5. Model accuracy on natural voice remains unverified.

Baseline comparison run:
https://github.com/Harrokk/Myai/actions/runs/38282373164

The user asked to continue investigating recognition accuracy,
not to record their voice again.

## Changes

`scripts/ventuno_whisper_base_swedish_comparison.py` now injects a
small, self-contained normalization/Levenshtein metrics helper
into the ephemeral Whisper inference subprocess.

For each of the 8 synthetic comparison trials, the helper derives
these **bounded, nontextual** outputs:
- Edit distance from exact reference, bucketed to
  `0`, `1-2`, `3-5`, `6-10`, `11+`.
- Number of decoded whitespace-separated tokens in the ranges
  `0`, `1-2`, `3`, `4-6`, `7+`.
- Count of the target words present, 0..3.
- Count of target words at matching positional indices, 0..3.
- Whether the three target words are found in their intended order.
- Whether the exact three-word sequence is found contiguously.

The recognized string is used **only inside the worker** and is
deleted immediately after deriving these metrics; the parent
validates and only returns allowlisted values. This is diagnostic,
not a license to change the safety-critical exact voice-command
allowlist or to guess the real user's discarded transcript.

The work runs with the **same** fixed question, two eSpeak
speaking rates, the same pinned Tiny/Base multilingual weights,
CPU and RAM limits, and no microphone, speaker, Ollama,
GenieX, production profile or new persistent model deployment.

## Verification

An initial workflow run
https://github.com/Harrokk/Myai/actions/runs/38283210256
passed 110 unit tests but failed one new unit test's incorrect
expectation for word position in reordered text. No models
were run in that failed attempt.

Correction is in commit
`e869e381c5e05619405b4c1f2feefd9c2096912a`.
**Final corrected VENTUNO model run is not yet independently
verified at the creation of this checkpoint.** Do not claim
a particular distance or word-overlap result until examining
its actual self-hosted CI logs.

Next: if the decoded synthetic utterances are nowhere near the
reference, investigate independent, properly licensed Swedish
reference speech of this exact phrase or alternative voice
synthesizers. If the output is near, investigate normalization,
beam settings and robust but strictly whitelisted transcript
variants. Live microphone tests still require new authorization.


## Verified VENTUNO Q proximity measurement

The corrected full self-hosted ARM64 run completed with every
step green:

- Source commit: `e869e381c5e05619405b4c1f2feefd9c2096912a`.
- Run: https://github.com/Harrokk/Myai/actions/runs/38283378612
- Job `114925795888`, conclusion **success**.
- **111/111** unit/security tests passed.
- Tiny and Base weights were verified and loaded separately,
  and synthetic cases were recognized offline. Active services
  remained healthy, with model/audio files cleaned afterward.
- **0 of the 8** recordings produced an exact match.
- Seven trials had edit distance **6–10 characters**;
  the closest was Tiny / slow speaking rate / beam 5,
  edit-distance bucket **3–5 characters**.
- For every one of 8 outputs, the decoded words had
  **0 aligned target-word positions**, no complete target
  word sequence in order, and no contiguous target phrase.
- Target-word overlap: Tiny had 0/3 in three cases,
  1/3 in its closest case; Base had 0/3 in one case,
  1/3 in three cases.
- **No decoded output contained more than one** of the
  three target words. This is not a punctuation-only
  failure and does not support relaxing the dialogue
  command match threshold.
- The original decoded strings were not saved or printed,
  and therefore cannot be reconstructed from the run logs.
- Worker peak RSS measured about **240 MiB** (Tiny) and
  **318 MiB** (Base), not representative of full-system
  cold-start or multi-model memory peaks.

### Recommendation after this evidence

Do NOT silently turn on fuzzy phrase matching for arbitrary
live microphone transcription. The 0–1 target word overlaps
suggest a materially different decoded phrase, not a
minor punctuation or spacing variation.

More useful controls: a natural human pronunciation of the
exact Swedish question, with source/rights and sample identity
verified, and a longer innocuous Swedish test sentence.
The existing eSpeak NG pronunciation may be a poor proxy
for actual spoken Swedish. If independently licensed
sample audio cannot be sourced, test a separately generated
higher-quality Swedish voice in a disposable environment.

No new microphone or loudspeaker test was authorized in
this diagnostic stage. The running Whisper default,
MyAI/GenieX services and installed Ollama remain unchanged.
