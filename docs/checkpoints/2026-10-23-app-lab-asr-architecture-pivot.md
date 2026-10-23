# VENTUNO Q: use first-party Arduino App Lab audio Bricks, keep MyAI's GenieX

**2026-10-23 — SOURCE-ONLY DRAFT, no deployment or audio permission.**

The user's third single-use physical smoke test confirmed the cue was heard
and the operator spoke `Vad heter du?` about one second later. The custom
Whisper Tiny CPU isolated capture nevertheless rejected it; original audio
and transcript were deleted. Stop interpreting that failure as proof the
user spoke prematurely or that the GenieX language model failed.

## Grounded interfaces, not invented dependencies

- Arduino's official VENTUNO Q local AI assistant guide (revised
  2026-10-13): https://docs.arduino.cc/tutorials/ventuno-q/local-ai-assistant
  Uses ASR Whisper Small (quantized), Qwen3-4B and a Kokoro TTS custom Brick.
  The sample uses a state machine and stops ASR before loading the LLM.
- Arduino's maintained Edge Dictation Assistant example:
  https://github.com/arduino/app-bricks-examples/tree/main/inspirational/platform_ventunoq/edge-dictation-assistant
  Its current `python/main.py` imports
  `from arduino.app_bricks.asr import AutomaticSpeechRecognition` and
  reads `chunk.type` / `chunk.data` from `asr.transcribe_stream()`.
  The README also mentions `transcribe_mic_stream()`; determine the
  installed App Lab Brick's actual interface before any physical use.
  Its application UI handles `partial_text` and `full_text`; **only**
  `full_text` may enter MyAI's model.
- Arduino's first-party Edge Speech Assistant:
  https://github.com/arduino/app-bricks-examples/tree/main/inspirational/platform_ventunoq/edge-speech-assistant
  uses `from arduino.app_bricks.tts import TextToSpeech`, `speak(text)`
  and `cancel()`. Prefer assessing this supported Brick before
  integrating custom Kokoro. Swedish voice quality must be measured
  before choosing TTS, not assumed.
- Our frozen profile has GenieX
  `qualcomm/Qwen3-4B-Instruct-2507:W4A16` at
  `http://127.0.0.1:18181/v1` and `voice.stt_model=small`;
  the *physical* smoke used a separate Whisper Tiny CPU process,
  with a five-phrase allowlist.
  `voice.enabled`, `voice.tts_enabled`, `voice.handsfree_enabled`
  remain false. Existing live services and tools stay unchanged.

## New source-only boundary

`scripts/ventuno_app_lab_readonly_asr_bridge.py` is an inert,
testable **text-only** gate. No Arduino runtime imports, I/O, networking,
model download, microphone opening, tool scheduling or output playback.
An external separately consented App Lab process would supply
`full_text` only. No final segment can pass twice; `partial_text`
never triggers an LLM. Raw text is process-local, absent from object repr
and logs. It accepts normal harmless Swedish questions, rather than
five fixed phrases, but conservatively refuses obvious risky requests
and exact cue echoes. The textual risk heuristic alone is **not** a
security boundary.

`answer_readonly_geniex` only calls an explicitly supplied, validated
`GenieXClient.chat` at the known loopback base URL, with no MyAI tools,
memory writes, planner or system authority. Tests use fake clients
and cannot reach any local service. This isolated read-only pathway
**does not yet integrate MyAI's memory/tool system**; it proves the
minimal safe text handoff before introducing app/container permissions.

## Required next gates

1. Confirm whether App Lab is installed, which ASR Brick API version
   exists, whether Swedish `sv` language is selectable, and whether
   quantized Whisper Small can run in the existing container with the
   concurrent GenieX process. Use source/config reviews and never
   trigger hardware remotely without separately approved supervised test.
2. Determine network namespace isolation: App Lab container loopback is
   not automatically the VENTUNO host GenieX loopback. Do not bridge
   GenieX to `0.0.0.0`, expose tokens, or assume an endpoint works.
3. Review ownership of ALSA microphone and speaker and app/model RAM
   contention; only one Brick may hold capture at any moment. Preserve
   existing 1.5 s handoff or a measured equivalent.
4. After a new explicit physical opt-in: manually test App Lab ASR with
   a visible on-device transcript for an operator-approved harmless
   phrase in a private UI (do **not** publish transcripts to CI).
5. Separately opt-in to local Qwen3 read-only answers, then test TTS.
   Only after this works should MyAI's existing permissioned tools,
   memory lifecycle and safety audit be reattached.

**NO-GO** for GitHub self-hosted audio jobs, microphone activation,
App Lab start, model downloads/installation, new TCP listeners,
production configuration changes, service restarts, main merge,
and continual wake-word listening.
