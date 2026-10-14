# MyAI checkpoint – controlled real human Swedish speech vs Whisper Tiny/Base

Date: 2026-10-14
Repository: Harrokk/Myai
Branch: dev/routing-boundary-followup
VENTUNO target: Arduino VENTUNO Q, Ubuntu ARM64, self-hosted label ventuno-q

## Scope and integrity

Goal: investigate why synthetic Piper Swedish speech succeeded on the exact phrase
"Vad heter du?" while the user's earlier microphone attempts were rejected.
DO NOT assume a success on synthetic speech proves reliable natural Swedish STT.

Independent natural voice reference: one human-spoken Shtooka Project recording
archived at Wikimedia Commons, described in its 2007 file revision as "Hur mår du?".
Speaker is a Swedish woman from Gotland. Attribution: M. Kihlstedt and N. Vion,
CC BY 2.0 France. Source:
https://commons.wikimedia.org/wiki/File:Sv-(conversation).ogg
Pinned specific historical audio bytes (not the **current** file at this title):
https://upload.wikimedia.org/wikipedia/commons/archive/1/1d/20071106020716%21Sv-%28conversation%29.ogg

Exactly 15,152 bytes Ogg and SHA256:
e83b36079bcd2c001c0a8466961f503923bdbb7e5fb14e6d5f93e981bc636e4b

The historical Commons file has *multiple uploads with different spoken
phrases*, so always use the exact pinned archive URL and digest; the current
description/filename is insufficient to identify the content. The expected
phrase is grounded in the historical file comment but was not independently
verified against the original recording by a Swedish human listener.

Source fingerprint on actual VENTUNO:
https://github.com/Harrokk/Myai/actions/runs/38507210855
Source fingerprint commit: 873bfb0d182bf9152f0bcd153a04dd81b735d541

## Code and tests

- scripts/ventuno_natural_swedish_stt.py: fixed URL, SHA256, buffer limit;
  pinned Tiny model; original sound plus USB-shaped 3s sample;
  beams 1 and 5; sanitized match and edit-distance-band results.
- tests/test_ventuno_natural_swedish_stt.py: authorization gates, hashes,
  wrong workspace, symlinks, resource limits, unsafe response rejection.
- scripts/ventuno_natural_swedish_base_followup.py: pinned Base comparison,
  same audio, independent bounded worker, no persistent installs.
- tests/test_ventuno_natural_swedish_base_followup.py.
- .github/workflows/ventuno-natural-swedish-stt.yml: ARM64 runner,
  isolated virtualenv, pinned model weights, model baseline, strict
  disabled production voice setting, always cleanup.

Main verification commit:
48fab939e07ddd39993189be56bd5917741d0e95
Actual verified comparative workflow:
https://github.com/Harrokk/Myai/actions/runs/38507835110
Job: 115669308718, SUCCESS.
55 / 55 relevant safety and regression tests passed; full MyAI tests
for this workflow commit also passed (run 38507835039).

## Real measured outcomes (NOT inferred)

One **human reference recording**, not 4 statistically independent
speakers or 4 independent phrases, was tested under four decoding
configurations per model:

Tiny:
- Original beam 1: incorrect, edit-distance band 3–5, 1/3 target words
- Original beam 5: incorrect, band 3–5, 1/3
- 3s padded beam 1: incorrect, band 6–10, 0/3
- 3s padded beam 5: incorrect, band 3–5, 1/3
- 0/4 strict exact matches; peak Whisper worker RSS 246.7 MiB.

Base:
- Original beam 1: incorrect, edit-distance band 6–10, 0/3 words
- Original beam 5: incorrect, band 1–2, 2/3 words
- 3s padded beam 1: incorrect, band 6–10, 0/3 words
- 3s padded beam 5: incorrect, band 1–2, 2/3 words
- 0/4 strict exact matches; peak Whisper worker RSS 334.0 MiB.

Both models used verified pinned multilingual model weights, CPU INT8,
Swedish transcription mode, no expected phrase prompt, and model
instances loaded sequentially rather than at the same time. The Base
weight revision and SHA256 are pinned in the existing project:
scripts/ventuno_whisper_base_swedish_comparison.py.

Earlier reference comparison:
- Piper Alma synthetic "Vad heter du?": 8/8 exact across Tiny/Base,
  two speed variants, beams 1 and 5.
- eSpeak NG synthetic same phrase: 0/8 exact.
- Independent Piper workflow: https://github.com/Harrokk/Myai/actions/runs/38284679674

These are NOT matched speaker/question experiments; **no general
word-error-rate, user-microphone reliability, or population-level success
rate can be derived from the 0/4 or 8/8 counts.**

Base beam 5 is *closer* to the human-reference string than Tiny under
this single example, but still not exact. Do NOT deploy Base merely
based on these data. The mismatch could involve acoustic conditions,
very short speech duration, original archive labeling, or ASR bias.
This test cannot distinguish these root causes.

## Operational safety and preservation

- No live microphone or speaker opened.
- No private recordings or raw decoded transcripts persisted or logged.
- No MyAI, GenieX, installed Ollama, runner configuration or production
  voice settings changed; both production services verified active.
- Temporary public audio, Whisper models and Python wheels removed on
  completion. The only durable writes were to GitHub source and this
  checkpoint.
- Per user instruction, defer investigation/remediation of runner
  boot-start/restart conditions. Do not change its systemd unit now.

## Next action when user requests further MyAI development

1. Find an **independently licensed, truly human-spoken recording of the
   exact phrase "Vad heter du?"**, preferably two distinct speakers,
   with a verifiable transcription. An alternate longer Swedish
   multiword clip with a different speaker is useful if exact phrase
   licensing cannot be established.
2. Verify immutable audio provenance, rights, content, size, and SHA
   before running. Inference remains audio-device-free and temporary.
3. Compare multiple natural utterances to evaluate hypothesis that
   tiny short utterances cause unreliable recognition and to
   distinguish mislabeled archive content from recognition failures.
4. Never silently loosen command allowlists, enable handsfree,
   persist user speech, or change GenieX production default.
5. A real user microphone capture still requires **fresh, explicit
   one-time authorization** with safe timing controls.
