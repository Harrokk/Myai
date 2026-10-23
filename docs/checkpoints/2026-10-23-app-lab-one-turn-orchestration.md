# App Lab one-turn orchestrator – official ASR Brick, no device execution

**2026-10-23; DRAFT; source-only; no physical permission carried over.**

This increment stages `scripts/ventuno_app_lab_one_turn.py` on top
of DRAFT PR #361. It is a *small glue component*, not a new
recognizer or a replacement AI model.

Official references:
- https://docs.arduino.cc/tutorials/ventuno-q/local-ai-assistant
- https://github.com/arduino/app-bricks-py/tree/main/src/arduino/app_bricks/asr
- https://github.com/arduino/app-bricks-examples/blob/main/bricks/arduino/asr/04_stream_mic_transcription/python/main.py

## Turn contract

An independently permitted App Lab entrypoint will eventually construct
`AutomaticSpeechRecognition(language="sv")` and explicitly start the
source as required by the App Lab Brick lifecycle. `ArduinoBrickOneTurn`
never imports Arduino modules or opens a microphone. On one explicit
user action it invokes `asr.transcribe_stream(duration=5)` *once*,
ignores partial events, examines the first `full_text`, and closes the
stream and calls `asr.stop()` before any LLM call.

Existing `ArduinoASROneShotGate` strictly prevents rearming; valid
natural harmless Swedish questions can pass but commands and wake/cue
echoes are conservatively blocked in this read-only prototype. No
raw transcript or full reply is returned in report, logs, exception
messages, or GitHub Actions. In a future operator-authorized private
UI, an explicit `private_final_handler` could receive the raw words
*after ASR release*; WebUI's default broadcast is **NOT** suitable.

Optional read-only local GenieX answer uses the existing PR #361
`answer_readonly_geniex` gate; a separate explicit LLM opt-in,
caller-supplied validated local client, and a 1.5s post-release pause
are mandatory. No tool registry, planner, MyAICore writes, TTS playback
or external HTTP listener is connected. A real App Lab container's
`127.0.0.1` may not refer to the host GenieX at all; **no network
bridge or `0.0.0.0` listener may be enabled to work around this**.

## Important privacy finding about first-party WebUI

The official `arduino.app_bricks.web_ui` defaults to binding
`0.0.0.0:7000` and `send_message(type, value)` **broadcasts to all
connected clients**; the optional `room=` scopes a message to a
specific session. A future microphone UI must require an independently
reviewed authentication/local-access and per-session policy before
showing private transcriptions. A plain `start_dictation` event from
an unauthenticated network browser is not adequate user authorization.
**This PR intentionally does not ship a microphone-enabled WebUI app.**

## CI and future gates

Mock-only tests cover: no authorization, strict first-final selection,
blocked echoes/unsafe prompts, invalid ports, exceptions, stop
failures, privacy-safe status-only reporting, stage ordering
ASR context close → microphone stop → 1.5s pause → read-only GenieX,
and rejection of nonlocal GenieX clients.

Next independent gate: determine the installed App Lab ASR Brick version,
microphone ownership with production services, availability of
`whisper-small-quantized`, and how to reach the host GenieX via a
strict local authenticated interface without exposing a new port.
Only thereafter stage a separately approved, manually started
App Lab voice pilot with a private session UI.

**No user microphone audio, GitHub self-hosted workflow, downloads,
service modifications, production config writes or deployment.**
