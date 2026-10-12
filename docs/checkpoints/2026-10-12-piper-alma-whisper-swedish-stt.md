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
