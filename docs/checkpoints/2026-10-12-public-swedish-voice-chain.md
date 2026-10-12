# VENTUNO Q – Swedish public-fixture STT -> GenieX -> WAV integration

Date: 2026-10-12
Branch: `dev/routing-boundary-followup`
Status: **integration run initiated; result not yet verified in this checkpoint**

## Physical USB audio: proven, but not accessed by this integration

- Real 2 s USB microphone recording succeeded with `plughw:1,0`
  (64,000 bytes, 16 kHz, status `microphone-signal-measured`).
  GitHub run: https://github.com/Harrokk/Myai/actions/runs/38249279855
- The USB speaker accepted 2.09 s of volume-limited Swedish eSpeak
  WAV at `plughw:1,0` (successful `aplay` exit), and the user
  separately **confirmed hearing** “Hej. Jag heter My AI.”
  GitHub run: https://github.com/Harrokk/Myai/actions/runs/38250308186

## New staged integration

- `scripts/ventuno_stt_gated_geniex_voice.py` uses the pre-existing,
  pinned `Systran/faster-whisper-tiny` multilingual CPU model,
  through `scripts/ventuno_whisper_tiny_cpu_smoke.smoke`.
- The input is **only** the publicly licensed, SHA1-pinned
  `Sv-svenska.ogg` pronunciation sample (Peter Isotalo, Wikimedia
  Commons; CC BY-SA 3.0 / GFDL), not user speech.
- The Whisper inference process runs with its existing resource
  limits and exits before GenieX or TTS are used. The gate refuses
  to proceed unless that actual STT result confirms the Swedish
  reference word and validated model weights.
- After a minimum RAM check, the proven existing
  `run_live_voice_bridge` submits one fixed safe prompt to the
  **already running** local GenieX, sends its response through the
  actual MyAI `VoicePipeline`, and renders Swedish WAV with a
  temporarily staged eSpeak NG. The bridge deliberately injects
  a **synthetic** STT trigger (not live microphone PCM).
- It writes no microphone audio, reference transcript, generated
  answer or synthesized WAV to logs or the repository. No
  microphone or speaker device is opened.
- The entire isolated ARM64 Python environment, Whisper model,
  public fixture, package cache and temporary eSpeak files are
  removed in an always-run step; production services and voice
  flags are not changed.

Workflow:
`.github/workflows/ventuno-public-whisper-geniex-tts.yml`
Source/CI trigger commit:
`0a4d3f80706d2742c8154a5bb25cff7d12ab9977`

**Important:** This is a real Whisper STT-success-gated,
live-GenieX-to-Swedish-WAV **staged integration**, not a demonstration
of actual microphone-to-LLM data flow, physical duplex audio,
echo cancellation, full conversation recognition, or persistent
handsfree mode. Those later stages require additional integration
work, fresh user authorization for real audio I/O, and rollback
planning.

## Next acceptance gate

1. Verify targeted regression suite and VENTUNO GitHub Actions result
   from the source commit.
2. Confirm the single local GenieX response and WAV synthesis succeeded,
   with no production service restarts.
3. Before live spoken conversation, build a staged interface that passes
   verified *real* STT transcript into the full MyAI request path with
   safe content filtering, microphone release and bounded TTS output.
4. Do not switch on production `voice.enabled`, `tts_enabled`
   or `handsfree_enabled` yet.


## Verified real VENTUNO Q integration result

The staged integration completed successfully on the actual
Arduino VENTUNO Q GitHub self-hosted ARM64 runner:

- Exact integration source commit: `0a4d3f80706d2742c8154a5bb25cff7d12ab9977`.
- Run: https://github.com/Harrokk/Myai/actions/runs/38251463045
- Job: `114818577022`, conclusion **success**.
- **55 of 55 targeted regression tests passed**.
- Installed ARM64 `faster_whisper` and `ctranslate2` imports were
  verified in the throwaway venv (`av 18.1.0`).
- Initial resource measurements: `MemAvailable` approximately
  **13,090 MiB**, free storage **33,911 MiB**; those are point-in-time
  checks, not long-term headroom guarantees.
- Public Ogg pronunciation fixture size **22,879 bytes**, SHA1
  verified against the pinned test fixture.
- Pinned multilingual Whisper Tiny CPU recognized the public
  Swedish word: `public_fixture_whisper_verified=true`.
- Whisper child process exited **before** GenieX call, to prevent
  the STT and LLM workloads from accumulating in one process.
- A single bounded response from the **already running local
  GenieX model** passed through the **actual MyAI VoicePipeline**
  and was synthesized via temporary Swedish eSpeak.
- Verified WAV metrics: **1.26 s**, **22,050 Hz**,
  normalized RMS **0.077133**.
- No real user microphone recording, physical speaker playback,
  transcript logging, WAV file storage, production service restart,
  production voice-enable change, or second LLM model load.
- All downloaded/staged STT weights and eSpeak packages were
  removed from the dedicated runner temporary checkout afterward.
  Both MyAI and GenieX services were confirmed active.

### Important interpretation

**PASS means integrated stage handoff, not handsfree dialog.**
The speech recognizer used the public sample solely as a verified
gate; the existing GenieX bridge deliberately injected a fixed
synthetic transcript. Therefore this did **not** test dynamic
transcript-to-MyAI-request forwarding. No production settings
should be switched on based on this test alone.

Next engineering milestone: a safe, bounded dynamic transcript
handoff from real Swedish STT into a MyAI request, starting with
verified public audio and no physical I/O; then separate consented
live-microphone + speaker conversation tests.
