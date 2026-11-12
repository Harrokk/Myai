# 2026-11-12: Whisper Small ASR native output and official RAM-WAV alternative

## Verified evidence
- User's 2026-11-12 App Lab test had a clean Python exit 0 with
  `microphone-opened-wait-for-capture`, `capture-started-speak-now`,
  `empty-final-only`.
- Full ASR Brick log confirms model `whisper-small-quantized`,
  language `sv`, translate false, 16kHz mono 16-bit; 125 2,048-byte audio
  chunks reached backend during the real approximately eight-second session,
  and native VAD generated speech_start.
- Native Whisper did not send a normal final and `speech_end` only occurred
  on teardown; final path printed
  `Non-supported or nn language detected!!!! code=nn`,
  `result_code=2`, empty transcription, with `mEverDetectedSpeech=1`.
- Service parsed VAD 700 ms as 70 frames (10 ms each). Do not change VAD
  based on an unsupported unit assumption.
- Upstream official OpenAI Whisper tokenizer maps `sv` to Swedish and
  `nn` to Nynorsk, **both valid upstream**. Native Qualcomm wrapper may
  apply its own semantics; without its source we do not know why its
  `Non-supported or nn` guard triggered, or the meaning of result_code 2.
- Pubic Oct-15 VENTUNO Q example (Philippe) recorded a WAV and used
  Arduino `WAVAutomaticSpeechRecognition` with success in French.
  Does not establish that it will work in Swedish with Kraken V3 X.
- Official SDK `local_asr_wav.py` accepts in-memory WAV bytes.

## Implemented as source-only, separate DRAFT
- `integrations/arduino_app_lab/asr_v2_official_wav_pilot` is distinct
  from both streaming v2 and archived legacy.
- One <=8-second vendor ALSAMicrophone capture in RAM, stop mic, build WAV
  bytes via standard library, call official WAVAutomaticSpeechRecognition
  with Swedish `sv`, no extra cloud/recording/file.
- Fixed private status codes, clear one-shot lifecycle and cleanup; fake
  synthetic tests only, no physical test or app import.
- Future decision: only consider a separate operator-approved physical
  test if source-only CI passes; read-only checks of current ALSA card and
  no service interference required.

## Explicit non-claims
- `nn` does **not** prove that the user spoke Nynorsk, that the model
  lacks Swedish, or that Qualcomm's enum 2 is a specific error.
- Source-only CI does not prove real-time accuracy, VAD, backend resource
  compatibility or hardware performance.
- No previous consent authorizes another live capture.
