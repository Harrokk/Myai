# VENTUNO Q – Piper Alma synthetic Swedish voice ASR comparison

Date: 2026-10-12
Repository: Harrokk/Myai
Branch: dev/routing-boundary-followup

## Prior evidence and goal

On the actual VENTUNO Q, the earlier eSpeak NG synthetic version
of the short phrase "Vad heter du?" was rejected in all 8 combinations
of Whisper Tiny/Base, beam widths 1/5 and normal/slower speech.
Proximity testing found 0 aligned target-word positions on every trial,
and no result had more than one of the three target words present.
Reference:
https://github.com/Harrokk/Myai/actions/runs/38283378612

This task tests whether a higher-quality Swedish synthetic voice can
supply clearer *reference speech* to the **same** pinned Whisper models.
It does **not** authorize the user's microphone or enable voice on the
active MyAI instance.

## Model provenance, rights and immutable checks

Voice: Piper **Alma medium**, Swedish sv_SE, 22,050 Hz, trained on
the NST Swedish TTS corpus with studio recordings. The per-voice
MODEL_CARD states **CC BY 4.0** for the model weights; record attribution
when distributing results or any eventual deployment. Source:
https://huggingface.co/rhasspy/piper-voices/blob/main/sv/sv_SE/alma/medium/MODEL_CARD

Model weights `sv_SE-alma-medium.onnx`:
https://huggingface.co/rhasspy/piper-voices/blob/main/sv/sv_SE/alma/medium/sv_SE-alma-medium.onnx

The source's SHA-256 of the 63.4MB ONNX weights is pinned to:
`f75455eb6afeb1db9e2905d5bd7e4115afcd3710e0d399b6a40981766d32fedc`.

Source Hugging Face revision `834f232` is used as a version
locator, **but** real model acceptance requires the explicit
full SHA-256, file size and Swedish voice/config checks. If the
revision or asset cannot be retrieved, fail closed. The exact
configuration must identify Swedish, Alma and 22,050 Hz.

Piper execution environment is staged from the official **Piper TTS
1.8.0 ARM64 PyPI wheel**, independently pinned to SHA-256
`3f60c1917de6d8e8033f395878ad3f88f6dfee88a8b05f98971a275f76a38484`.
Official artifact:
https://pypi.org/project/piper-tts/1.8.0/

Version-pinned secondary runtime dependencies are installed only
into a disposable separate Piper venv, and never into MyAI,
GenieX, Ollama or system paths. The Piper Python package is licensed
GPL-3.0-or-later, distinct from the Alma model weight license.
Record and review these respective conditions before considering
persistent deployment.

## Test execution rules

- Files:
  `scripts/ventuno_piper_alma_swedish_stt.py`
  `tests/test_ventuno_piper_alma_swedish_stt.py`
  `.github/workflows/ventuno-piper-alma-swedish-stt.yml`.
- Only the fixed test question "Vad heter du?" is synthesized.
- Two neural Piper speech rates: normal 1.0 and slightly slower 1.25.
- Piper creates WAV **in RAM** in a short-lived isolated CPU subprocess.
- Convert to the previously validated 3-second/16 kHz/mono/S16_LE
  USB-compatible synthetic waveform, adding 350ms leading silence.
- Decode each synthetic waveform using separately loaded,
  previously verified multilingual Whisper Tiny and Base with
  beams 1 and 5, with no expected transcript prompt.
- Output only strict-match booleans, clipped distance bands,
  target-word overlap and alignment, with coarse runtime/RAM
  measurements. No raw transcript, WAV/PCM or model reply is saved.
- Fail closed on missing model checksums, incorrect files, low memory,
  incompatible Piper ARM64 wheel, missing runtime dependency,
  invalid waveform or unexpected model metadata.
- No microphone, speaker, MyAI/GenieX/Ollama request, service restart,
  system package installation, persistent model installation
  or voice settings changes.
- All staged runtime, voice, model data and test files are removed
  after the CI attempt.

## Verification status

The workflow source was added in commit
`8f4262a9360e4b4ce78f373792fed1c1ff1f8e5c`.

**The actual self-hosted VENTUNO Q Piper-to-Whisper run has not
yet been independently checked at checkpoint creation.** A failed
dependency installation or source checksum is a blocked test,
NOT a negative Swedish recognition result. Do not claim
recognition improvement unless the verified run completes.


## Actual VENTUNO Q results: all eight Piper Alma recognitions succeeded

The genuine self-hosted ARM64 run completed with all steps
successful:

- Exact workflow source commit:
  `8f4262a9360e4b4ce78f373792fed1c1ff1f8e5c`
- Run: https://github.com/Harrokk/Myai/actions/runs/38284679674
- Job: `114930090247`, conclusion **success**.
- **120 / 120** targeted mock/security/regression tests passed.
- The official Piper ARM64 1.8.0 wheel was SHA256-verified and
  installed only into a disposable virtual environment.
- The Swedish Piper Alma model was downloaded with an immutable
  revision locator; actual ONNX weight SHA256 verified against
  `f75455eb6afeb1db9e2905d5bd7e4115afcd3710e0d399b6a40981766d32fedc`.
- Two in-memory Piper variants (normal speaking speed and
  25% slower) were converted to the same 3 s / 16 kHz /
  mono S16_LE recording format as the previous eSpeak
  synthetic test and the physical USB microphone.
- Identical pinned multilingual Whisper Tiny and Base, with
  decoding `beam_size=1` and `beam_size=5`, were run
  in separate CPU processes, without expected-text prompting.
- **8/8 strict exact phrase matches** for
  `Vad heter du?` after plain normalization.
  Every decoded result contained all 3 correct words,
  all 3 at the expected positions and in order.
  The edit-distance band was **0** for every result.
- Tiny: **4/4**; Base: **4/4**.
- Whisper worker peak RSS ~**236.2 MiB** for Tiny, ~**314.9 MiB**
  for Base (does not include Piper render peak or concurrent
  MyAI end-to-end memory use).
- No user microphone, real speaker, real user recording,
  networked model provider chat, or production voice service was
  involved. Whisper/Piper temporary model files, WAV and checkout
  were removed. MyAI/GenieX stayed active and local Ollama
  installation was untouched.

### Engineering interpretation

Compared with the earlier eSpeak-generated synthetic question,
which had **0/8 matches** in the identical model/beam matrix,
Piper Alma's higher-quality Swedish question had **8/8 exact
matches**. This strongly suggests **the synthetic eSpeak
pronunciation was an unreliable evaluation input**, not that
Whisper Tiny fundamentally cannot transcribe this Swedish
question.

**Important limitation:** This does NOT establish the cause of
the real user's two rejected microphone utterances. The original
physical audio was deliberately discarded, so possible recording
timing/position/USB capture quality, surrounding sound and
ASR-specific errors remain unverified. The Piper-generated
speech is still synthetic, not a natural human recording.

### Next recommended gate

1. Retain Whisper Tiny (beam 1) as the minimal-resource
   candidate for the next evaluation; do **not** deploy Whisper
   Base automatically since Base added no benefit here.
2. The next meaningful accuracy control is an independently
   licensed, verified human Swedish pronunciation of the
   **same** question, processed without mic or speaker.
3. If the user explicitly authorizes another one-time real
   microphone test, add a fresh audible cue and use only
   constrained diagnostic categories. Never infer previously
   discarded speech content or retry old approvals.
4. Do not loosen safe command matching, enable handsfree or
   replace the active GenieX/Ollama runtime as a response
   to this experiment.
