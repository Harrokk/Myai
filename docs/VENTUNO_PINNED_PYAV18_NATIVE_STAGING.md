# MyAI VENTUNO – pinned PyAV 18 and disposable native voice-stage

**Date:** 2026-10-16. **Branch:** DRAFT over PR #242, no merge to main.

## Confirmed conflict and correction

Our earlier 28-wheel package lock contained `av==19.0.1`, but the checked-in
`scripts/ventuno_voice_wheel_staging.py::STT_WHEELS` deliberately limits
PyAV to `av>=17,<19`. The checked-in comment records the reason:
`faster-whisper==1.2.1` still passes `metadata_errors` to `av.open`,
while PyAV 19 removed this parameter.

The host-only pinned resolver **successfully** resolved
`av==18.1.0` (CPython `cp311-abi3` portable to Python 3.12 on
`manylinux_2_28_aarch64`) and the remaining 27 wheels. Their exact
hashes are atomically updated in:

- `config/voice_arm64_cp312_wheels.lock.json`
- `requirements-voice-arm64-hashed.lock`

Static lock validation now refuses a superficially correct lock containing
PyAV other than 18.x. This is a bounded compatibility policy for the current
Whisper version, not a claim that PyAV 18 is the only possible future version.

## Synthetic end-to-end voice

`scripts/ventuno_remote_synthetic_e2e.py` invokes the real
`VoicePipeline` interface through the existing synthetic STT/assistant/WAV
bridge with a fixed generated sine wave. It verifies exactly-once TTS, WAV
signal, deliberately rejected silence, and a small Python allocation bound.
It does not call a real Whisper model, GenieX/Ollama, file-backed SQLite,
microphone, speaker, camera, user tools or NPU. Even a green outcome is **not**
a voice quality or performance claim; import/model/runtime tests are separate.

## Temporary board-native ABI staging (no I/O devices)

`.github/workflows/ventuno-voice-native-abi-stage.yml` first runs tests on
hosted Linux against exact head SHA. A subsequent **self-hosted ARM64** job
checks conservative free RAM and disk thresholds. Only if enough room
exists does it download **28 hash-pinned binary wheels** into a newly
created, private `RUNNER_TEMP` checkout, compare each hash to the in-repo
manifest, install offline into a disposable venv, perform `pip check`, and
attempt bounded Python imports:

`sounddevice`, `webrtcvad`, `pyttsx3`, `ctranslate2`, `av`,
`faster_whisper`.

It never constructs a WhisperModel, opens PortAudio devices, initializes a
TTS playback engine, accesses GPIO, loads GenieX or executes QNN/HTP.
Network requests are limited to pip wheel acquisition and Git clone;
all installed Python content lives under the newly created temp tree.
The wheelhouse, staging venv and checkout are removed by an unconditional
cleanup step. The running `/home/arduino/MyAI/.venv` is not modified.

**Remaining once this test is green:** Real native library import does not
prove correct STT behavior, missing sound drivers at playback, model
latencies or fully tested process termination under hardware load.
Physical audio, dedicated recovery and NPU profiling remain separate GO/NO-GO
gates and require a fresh physical operation authorization.

### Reproducibility and evidence

- `scripts/ventuno_voice_static_lock_check.py`: refuses version/hash drift
- `tests/test_ventuno_voice_static_lock_check.py`: rejects PyAV19 with
  forged, internally consistent manifest entries
- `tests/test_ventuno_remote_synthetic_e2e.py`: checks normal and failure paths
- GitHub Actions reports remain bound to exact final commit

No DRAFT merge, production update or physical audio authorization.
