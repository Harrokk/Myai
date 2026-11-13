# Pinned reference: operator-verified VENTUNO Q Alma ZIP (2026-11-13)

This document records **source verification of an uploaded local artifact**;
it does NOT claim the code is deployed by MyAI, nor does it copy the
operator's 63 MB model weights or original app into GitHub.

Input archive: Local-LLM-Piper-Alma-NoKeyword.zip
SHA-256: 3fe9070939603e6383f95f2a99b92e56eef6c665942d0e161db39d3f85234ec8
ZIP: 13 files, approximately 58.3 MB compressed, 63.5 MB expanded
App code: python/main.py SHA-256 f1d3f3e2ecc94197f3a452f1a13029f41c7778046d14dc28d7346c87c06f2a87
Voice: sv_SE-alma-medium.onnx, SHA-256 b4bfecd22e30cf28f514eeea06c0da440be1721435a652d0571ee65963ce8f65

The binary model SHA matches the attribution MODEL_CARD in the uploaded ZIP.
The MODEL_CARD names Daniel Nylander and CC BY 4.0. The Piper runtime uses
GPLv3; no source/model archive redistribution is part of this change.
The uploaded README claims an original LICENSE was preserved but there
is no LICENSE entry among the actual 13 files; packaging licensing must
be reviewed before redistribution of any modified app.

## Actual App Lab runtime behavior observed in source

- app.yaml: local arduino:llm, arduino:asr, piper_sv_tts, no keyword brick
- Mic: Microphone(device=Microphone.USB_MIC_1, shared=True)
- ASR: AutomaticSpeechRecognition(mic_asr) WITHOUT language forcing
- ASR stream: transcribe_stream(duration=7) then first full_text event
- Partial-text fallback if final absent, both after exceptions and normal timeout
- The ASR microphone is explicitly stopped with mic_asr.stop() AFTER a
  1.5-second pause; asr.stop() is only called in the app finally block.
  This does NOT prove model/ASR resources have been fully released.
- LLM: Arduino LargeLanguageModel with memory(5), Qwen-like local chat_stream
- Language: user receives a short Swedish answer via the prompt
- TTS: custom PiperSvTTS 9101 service, voice sv_SE-alma-medium;
  synthesizer settings noise_scale=.8, noise_w_scale=.6, length_scale=.9
- Playback: /tmp/assistant_response.wav and aplay -D plughw:1,0
- LED: sketch controls states 0/1/2/3 via Bridge
- Existing source logs partial/final user text and model output, which can
  expose user speech in App Lab logs. The exact uploaded App Lab app remains
  unchanged; future modified variant must redact logs.
- Prompt injects current time in America/Santo_Domingo, not Europe/Stockholm.
  Correcting local time is a separate future app patch, not changed here.
- A stale print string still says 'Speaking via Kokoro'; it does not mean
  the engine is Kokoro — actual import and service use Piper.
- Dockerfile installs piper-tts 1.8.0 and aiohttp >=3.9,<4; the first build
  requires network and the current image is not reproducible from hashes.
- The TTS brick binds 0.0.0.0 INSIDE its container, service 9101 exposed on
  the app-defined Docker network; app.yaml has ports: [].

## Interface policy

The original operator-approved app continues using its own Qwen/Alma loop.
Any proposed MyAI integration uses a separate version and MUST:

1. Never route partial_text fallback as an actionable tool command.
2. Require trusted host proof of session, stopped ASR microphone and Stop
   state; cooperative booleans alone are not physical proof.
3. Authenticate every final with the existing MyAI HMAC protocol, unique
   session/request IDs, kernel credential validation and strict 2 KiB framing.
4. Maintain read-only tools and disabled automatic memory writes until a
   separately reviewed consented write path exists.
5. Avoid microphone, TTS and NPU double ownership. Never start MyAI and
   App Lab recognition loops concurrently.
6. Carry the MyAI reply privately to the Alma speaker through a *future*
   authenticated response path. Do NOT add a publicly exposed WebUI or
   unauthenticated HTTP endpoint.
7. Keep the uploaded working app, original Zip, MyAI runtime, GenieX, and
   App Lab port declarations untouched until user-approved testing.

## This pull request

- Exact member digest allowlist and non-extracting ZIP verifier in
  integrations/arduino_app_lab/alma_reference/source_contract.py.
- Pure Python event gate recognizes Arduino's exact partial_text/full_text
  event structure; ONLY a bounded full_text is eligible for MyAI dispatch.
- Portable HMAC request encoder compatible with core/app_lab_unix_final_text.
- Synthetic tests only; no hardware, microphones, sockets, model loading,
  changing config, package downloads, Docker or service runtime.
