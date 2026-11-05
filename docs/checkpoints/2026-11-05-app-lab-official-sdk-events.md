# Official Arduino App Lab ASR API contract — source-only — 2026-11-05

## Verified vendor API

Read the vendor source and README directly (Arduino `app-bricks-py`, `main` commit `94f100ee906770e6f469f9edbc615bad895d695e`):

- `src/arduino/app_bricks/asr/README.md`
- `src/arduino/app_bricks/asr/local_asr.py`
- `AutomaticSpeechRecognition(language="sv", translate=False)`
- `transcribe_sentence_stream(timeout=N)` returns a context-managed `TranscriptionStream[ASREvent]`.
- `ASREvent` has `type` = `partial_text` or `full_text`, and `data` as the text.
- A finite nonzero timeout is required in a future App to bound waiting; SDK `timeout=0` is unbounded.
- The Brick manages the default microphone if passed none. Passing a microphone explicitly makes the App owner responsible for start/stop.
- Arduino VENTUNO local assistant guide recommends compatible `whisper-small-quantized` and an explicit mic release before heavy LLM execution.

## New MyAI separation

The new pure adapter `integrations/arduino_app_lab/asr_v2/sdk_events.py` accepts only an *already opened* SDK event stream provided by a future, separately authorized application. It **does not import Arduino SDK, open microphone, launch a process, load a model, issue LLM queries, save a transcription or call any tool**.

The code:
- validates an ASR object's read-only `language="sv"`, `translate=False`, `transcribe_sentence_stream`, `cancel`, and `stop` capabilities without invoking them;
- ignores partial_text and never accesses its data;
- consumes only the FIRST full_text through the existing one-shot gate;
- caps iteration at 64 events and closes the context on all outcomes;
- suppresses exception details and prevents private final text from leaking through `repr`;
- never authorizes a new physical recording or model query.

The event budget is not a wall-clock timeout. A future App must call `transcribe_sentence_stream(timeout=8)` while controlling the mic and must restore audio resources even if the ASR stream fails.

## Safety and next steps

No voice production setting, hardware runner, microphone, old `scripts/ventuno_usb_*`, previous App Lab pilot, GenieX service, or installed dependency is changed. Source-only CI uses a fake official SDK stream.

Next: package a separate operator-triggered Arduino App Lab ASR v2 pilot with a physical consent gate, source compatibility review and a safe stop path. That pilot is not yet shipped or authorized to run. Live microphone/Whisper Small accuracy on this particular VENTUNO is still unverified. The archive branch remains untouched.
