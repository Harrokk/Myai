# MyAI – VENTUNO Q: synthetic Swedish Whisper Tiny vs Base

Date: 2026-10-12
Repository: `Harrokk/Myai`
Branch: `dev/routing-boundary-followup`

## Problem addressed

The user confirmed hearing the USB headset cue and speaking the intended
three-second test question "Vad heter du?". Both physical microphone
recordings generated non-silent audio, yet pinned multilingual Whisper
Tiny returned nonapproved text, and subsequent completely **synthetic**
eSpeak-generated recordings of the same phrase at 175 and 130 words/minute
also failed Tiny's strict recognition check:
https://github.com/Harrokk/Myai/actions/runs/38281113234

The cause may be insufficient Whisper Tiny accuracy for short Swedish
utterances, unclear synthetic eSpeak articulation, or other acoustic
factors; no single explanation is proven.

## New comparison

- `scripts/ventuno_whisper_base_swedish_comparison.py`
- `tests/test_ventuno_whisper_base_swedish_comparison.py`
- `.github/workflows/ventuno-whisper-base-swedish-comparison.yml`

Models:
- Tiny: the previously tested pinned `Systran/faster-whisper-tiny`,
  validated against `model.bin` SHA-256.
- Base: `Systran/faster-whisper-base` multilingual (not English-only),
  pinned to revision `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`,
  with `model.bin` SHA-256
  `d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9`.
  Weight hash, file sizes, metadata and repository structure must
  verify before inference. License: MIT per model repository.

Test matrix: each model independently processes two offline Swedish
eSpeak utterances of **"Vad heter du?"** (175 and 130 WPM) using
`beam_size=1` and `beam_size=5`. The exact real USB capture frame
format is used: 3 seconds, 16 kHz, mono S16_LE, padded with 350 ms
of leading silence. Each inference process is separate and bounded
by CPU-time, virtual memory and wall-clock limits; both models are
never loaded simultaneously. The question is **not** supplied as
an `initial_prompt`, which would bias the measurement.

The only collected outcomes are a strict match boolean, a short
predefined error category and runtime and model-memory measurements.
Decoded text, PCM, synthesized speech and subprocess stderr are
not published, saved or logged. The entirely temporary pinned model
weights are removed in the workflow's always-run cleanup.

The real USB microphone and USB speaker are **never opened**.
No Ollama/GenieX calls, service starts, model replacement or persistent
production configuration changes occur. Both existing active services
are checked before and after.

## Acceptance criteria

1. Mocked security/unit tests pass on the self-hosted VENTUNO.
2. Pinned public Swedish reference word can still be decoded by Tiny.
3. Pinned Base model downloads and checksum verification pass.
4. All eight synthetic recognition combinations produce validated,
   sanitized results without writing raw audio or transcriptions.
5. Select the lowest-resource configuration that **actually recognizes**
   the phrase reliably in both synthetic variants. The live microphone
   will require separate user authorization later.

**Run result pending verification at checkpoint creation.** A CI
`success` without phrase matches counts as a **completed negative
diagnostic**, not successful Swedish speech recognition.


## Verified actual VENTUNO Q test result

After an initial trivial missing `argparse` import was fixed,
the entire comparison completed successfully on the actual
VENTUNO Q self-hosted ARM64 runner:

- Comparison source commit:
  `452bfbbea3b577eb5c1999624665180de6be8fd8`
- GitHub Actions run:
  https://github.com/Harrokk/Myai/actions/runs/38282373164
- Job `114922481879`, **success**, all workflow steps
  including staging, model integrity, measurements and cleanup passed.
- **103 / 103** targeted regression tests passed.
- Pinned multilingual Tiny passed its pre-existing licensed
  Swedish public pronunciation word control.
- SHA256-verified multilingual Base loaded correctly on VENTUNO
  using local ARM64 CPU.
- Both models processed exactly two offline synthetic Swedish
  pronunciations of "Vad heter du?", each with beam sizes 1 and 5.
- **All eight** strict full-phrase matching checks were false:
  Tiny: 0/2 with beam 1, 0/2 with beam 5;
  Base: 0/2 with beam 1, 0/2 with beam 5.
- All eight returned the coarse classification
  `other-unmatched`, meaning the decoded phrase was neither
  exactly the target nor an empty/two-word string. Exact
  decoded words were **not** logged or saved.
- Tiny CPU inference: 1.47–2.00 seconds per synthetic case/beam,
  model load 0.472 seconds, worker peak RSS ~242.5 MiB.
- Base CPU inference: 1.72–6.41 seconds per synthetic case/beam,
  model load 0.702 seconds, worker peak RSS ~322.8 MiB.
  These are limited synthetic one-off worker measurements,
  **not** end-to-end conversational latency benchmarks.
- No real microphone, physical playback, Ollama or GenieX
  calls were made; both active production services stayed running,
  and temporary model weights, synthetic audio and logs were removed.

### Engineering conclusion

**Upgrading from Tiny to Base alone did not improve recognition
of this exact synthetic Swedish short question**, even with
beam size 5. This does not imply that either model cannot
recognize Swedish generally, and does not prove a microphone
or Whisper decoder defect. eSpeak NG's synthetic articulation,
the particular short question, and strict literal phrase
matching all remain plausible contributors.

Do not change the running MyAI default STT model, enable
handsfree, or make another real microphone recording on the
strength of these results. Recommended next **synthetic-only**
diagnostic: quantify how close the eight decoded strings were
to the target without exposing any raw text (e.g. Levenshtein
distance bands, position/token agreement), and compare against
an independently sourced, natural or higher-quality Swedish
sample of the exact phrase if one can be license/identity
verified. Only authorize another physical mic test after
controlled accuracy improves.
