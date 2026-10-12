# MyAI VENTUNO Q – Ollama som frivillig andra LLM-motor

Date: 2026-10-12
Repository: Harrokk/Myai
Branch: `dev/routing-boundary-followup`

## User-approved goal

Enable a **locally running Ollama** on Arduino VENTUNO Q as an
alternative to Qualcomm GenieX for Swedish text replies. Keep existing
MyAI memory, tools, Whisper STT, offline eSpeak TTS, USB microphone
and speaker. Do **not** replace the active GenieX runtime or enable
handsfree automatically.

Ollama is an **LLM runtime**, not a drop-in replacement for Whisper
microphone-to-transcript or offline text-to-speech.

## Already present in MyAI, before this work

- `core/ollama_client.py`: implemented `/api/chat` text/stream client.
- `core/geniex_client.py`: Qualcomm GenieX client.
- `core/llm_factory.py`: existing selectable Ollama/GenieX providers.
- `core/resilient_llm.py`: opt-in fallback; the VENTUNO profile
  currently has fallback **disabled**.
- `core/config_validation.py`: VENTUNO production profile deliberately
  requires `llm.provider="geniex"`, which this work preserves.

## Verified VENTUNO Q observation

A read-only self-hosted ARM64 runner test completed successfully:

https://github.com/Harrokk/Myai/actions/runs/38263784770

- **19 tests passed** for local model readiness, factory and Ollama client.
- `ollama_binary_present=false`: Ollama not currently installed.
- `loopback_ollama_api_ready=false`: no running local Ollama server.
- `test_model_already_downloaded=false`.
- ~**12,899 MiB** available RAM, ~**33,916 MiB** free disk at
  measurement time (these quantities vary).
- Both active MyAI and GenieX services remained healthy.
- No model loaded, software installed or production config changed.

## Source changes

1. Development-branch `config/profiles/ventuno_q.json` now includes
   optional `ollama.url=http://127.0.0.1:11434/api/chat` and
   `ollama.model=qwen3:0.6b`, **without changing** GenieX primary or
   disabled fallback/voice flags.
2. `scripts/ventuno_ollama_readiness.py` detects only the installed
   executable, loopback API and local model presence. It never loads a
   model, starts a daemon, installs packages or logs model names.
3. `.github/workflows/ventuno-ollama-readiness-readonly.yml` checks
   profile validity, Ollama and GenieX factory selection and ARM64
   readiness, while preserving active production services.
4. `scripts/ventuno_voice_backend_selector.py` permits a strictly
   local, per-turn Ollama or GenieX **text answer** through the existing
   LLM factory. It validates the original GenieX production profile
   *before* temporarily selecting Ollama in memory; no persistent
   provider switch or automatic backend fallback occurs.
   Only the small named model and exact loopback endpoint are
   authorized for this staged path.
5. Regression tests verify no remote URL, larger Ollama model,
   unapproved voice command or unbounded reply can slip into
   the new isolated selector.

## ARM64 isolated binary + tiny model compatibility gate

Workflow:
`.github/workflows/ventuno-ollama-arm64-isolated-smoke.yml`

The workflow downloads the **official pinned** Ollama Linux ARM64
release asset `v0.34.0` (not an arbitrary install script or latest
mutable release). It checks the SHA-256 published by Ollama's
GitHub release:

`6a9e5b3650c2024d8a78da86b23876f6eea238657a3262d7e5ec0f3688c5d28e`

Only an isolated directory beneath `$RUNNER_TEMP` is used.
The server binds to `127.0.0.1:11435` (different from the
potential persistent 11434 service), uses a private temporary model
cache, downloads **only** `qwen3:0.6b` (~523 MB), attempts one short
Swedish chat response, then stops and removes its server binary,
temporary model and cache. It requires minimum free RAM/storage, has
bounded downloads and does **not** add a system service, install to
`/usr`, change MyAI settings or touch GenieX.

**Isolated run result must be checked separately**. This document
is not a claim that ARM64 binary inference or NPU acceleration has
succeeded, or that Ollama is persistently installed.

## Next gated actions

1. Inspect results of the pinned isolated ARM64 package + Qwen smoke.
   If it fails (missing zstd, checksum mismatch, incompatible binary,
   insufficient RAM, network blockage, or CPU timeout), identify the
   specific cause; do not bypass security checks to force deployment.
2. If isolated CPU inference succeeds, measure time-to-first-answer,
   RAM during overlapping GenieX and Whisper operations, and
   ensure model swaps do not degrade production voice latency.
3. Prepare a reversible user-local persistent Ollama installation
   **only after** compatibility and resource acceptance. Set the
   Ollama service to listen on loopback only. Keep GenieX as primary,
   model fallback disabled, and reserve memory headroom.
4. Test optional Ollama-answer backend with a **synthetic text**
   question, never a new microphone capture without authorization.
5. Only with verified safe performance consider a separate
   voice-mode Ollama opt-in. Production MyAI and GenieX are left intact.

Do not confuse the prior USB audio experiments with an Ollama
compatibility result. No new physical audio capture or speaker
playback was performed by this work.


## Verified persistent user-local Ollama installation

The previously missing Ollama runtime is now **installed persistently**
on the VENTUNO Q under the `arduino` home directory, without
replacing or restarting production MyAI or GenieX:

- Exact one-time authorization commit:
  `2955390c0fc508f880a99eb0fa8634546d89e8d7`
- Successful self-hosted ARM64 GitHub run:
  https://github.com/Harrokk/Myai/actions/runs/38266057773
- Job `114868389459`, all steps **success**.
- Official pinned Ollama Linux ARM64 **v0.34.0** artifact SHA256
  verified before unpacking.
- Installed in:
  `/home/arduino/.local/opt/myai-ollama/v0.34.0`
- Included model: `qwen3:0.6b` (~523 MB downloaded from the Ollama
  registry), held in that directory's `models/` cache.
- A short real Qwen3 text answer on the device succeeded; measured
  post-load single request latency **2.74 seconds** in the isolated
  test (not an end-to-end cold-start benchmark).
- Runnable loopback-only launcher:
  `/home/arduino/.local/opt/myai-ollama/v0.34.0/start-local-only.sh`
- The launcher is **not started as a permanent service**, no service
  auto-start was created, and no background Ollama server was left
  running after the job. GenieX continues as MyAI's production
  default and automatic fallback remains disabled.
- The temporary download archive/staging was removed. Active voice
  profile, microphones, speaker, MyAI and GenieX services were not
  changed.

A subsequent read-only inventory independently confirmed the
persisted executable:

https://github.com/Harrokk/Myai/actions/runs/38266892423

- **44 regression tests passed** (includes local backend selection,
  Ollama API client and memory-safe discovery).
- Ollama user-local binary present; local API correctly unavailable
  because the new server is intentionally stopped.
- ~12,760 MiB free RAM and ~31,280 MiB free disk at inventory time.
- Production services remained active.

The staged USB voice hardware driver can now accept a per-turn
`response_backend="ollama"` option, while defaulting to
`"geniex"`. No physical Ollama speech dialogue has been attempted.
Its synthetic safety suite passed **117 tests**:
https://github.com/Harrokk/Myai/actions/runs/38266474560

A separate one-time test is prepared to start the newly installed
Ollama launcher, ask exactly one safe text question through the
actual MyAI `OllamaClient`/LLM factory, and shut the launcher down
again; that test's own result must be checked separately.


## Installed Ollama real MyAI response verified

The installed Ollama runtime was started briefly via its persisted,
loopback-only launcher and the **actual existing MyAI OllamaClient**
was selected by `scripts/ventuno_voice_backend_selector.py`.
No model was downloaded for this test.

- One-time source commit:
  `7a289222976e98b5e7a608594c8dc642ddb45664`
- Successful VENTUNO Q run:
  https://github.com/Harrokk/Myai/actions/runs/38267233100
- Job `114872342246`; all steps **success**.
- **33/33** targeted regression tests passed.
- MyAI's original VENTUNO profile remained `llm.provider=geniex`,
  fallback **disabled**, voice/handsfree **disabled**.
- The per-turn Ollama option selected the installed
  `qwen3:0.6b` model through MyAI's `core.llm_factory` and
  actual `core.ollama_client.OllamaClient.chat`.
- Question was a fixed harmless Swedish text test
  (`vad heter du`), **not** a microphone recording.
- A bounded nonempty text reply (**49 characters**) was returned
  through the existing MyAI path. End-to-end request duration
  **8.53 s**, including any cold model load; no reply content was
  saved or logged. This is separate from the earlier warm
  inference measurement of 2.74 seconds.
- The locally started Ollama server was stopped, temporary
  logs removed, and GenieX/MyAI production services verified
  active. The installed Ollama binary and model were retained.

**Now verified:** GenieX and Ollama are selectable through MyAI's
LLM machinery, and Ollama works on physical VENTUNO Q ARM64 hardware.
Whisper speech-to-text and eSpeak text-to-speech remain separate
components. An actual microphone -> Whisper -> Ollama -> USB
speaker end-to-end voice exchange has **not** been authorized or
executed. No production provider switch or continuous Ollama
background service was enabled; those are separate acceptance gates.
The *entire* MyAI test suite was not rerun as part of these
targeted Ollama tests.
