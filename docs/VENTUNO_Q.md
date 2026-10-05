# MyAI on Arduino VENTUNO Q

This note describes the current migration path for Arduino VENTUNO Q / Qualcomm Dragonwing IQ-8275.

## Current safety model

The repository keeps the Windows/Ollama configuration as the default.

The VENTUNO profile is selected explicitly:

```bash
export MYAI_SETTINGS=config/profiles/ventuno_q.json
```

or by running:

```bash
bash scripts/start_ventuno.sh
```

The VENTUNO profile currently:
- selects GenieX for the main LLM
- prepares Qwen3-4B-Instruct-2507
- enables LLM response streaming
- enables microphone release/handoff before heavy inference
- keeps voice input/output globally disabled until hardware validation
- keeps VLM disabled until camera/NPU validation
- enables the VENTUNO platform profile but keeps STM32 RPC disabled
- keeps all STM32 RPC writes disabled
- contains empty RPC method allowlists

## Planned local AI services

Main LLM:

```text
ai-hub-models/Qwen3-4B-Instruct-2507
```

Local GenieX endpoint:

```text
http://127.0.0.1:18181/v1
```

Planned VLM:

```text
qualcomm/Qwen3-VL-4B-Instruct
```

The VLM remains disabled until it is verified on the actual board.

## Read-only preflight

Before starting MyAI on real VENTUNO hardware:

```bash
python3 scripts/ventuno_preflight.py
```

The preflight does not:
- call the STM32
- write GPIO
- actuate hardware
- run LLM/VLM inference

It checks the runtime profile, Linux ARM64, GenieX CLI, local endpoint configuration, Arduino Router Bridge availability, the Router Unix socket and RPC write policy.

## GenieX preparation

When the physical board is available, use the Qualcomm-supported GenieX installation for that image/runtime, then pull the configured model:

```bash
geniex pull ai-hub-models/Qwen3-4B-Instruct-2507
geniex serve
```

Do not automatically upgrade GenieX/QAIRT on a validated MyAI installation. Record and pin the versions that pass the hardware test.

## STM32 / Arduino Router

MyAI uses the official Python bridge package:

```bash
python3 -m pip install -r requirements-ventuno.txt
```

The default Router transport is the protected local Unix socket:

```text
/var/run/arduino-router.sock
```

MyAI's wrapper is fail-closed:
- RPC must be explicitly enabled
- write RPC must be separately enabled
- read and write method names have separate allowlists
- no raw arbitrary method call is exposed as a natural-language tool

The first physical RPC test must be read-only. GPIO/motor writes are deferred until the MCU-side watchdog and explicit safe methods are verified.

## Voice resource handoff

On VENTUNO Q, the voice state machine follows this resource order:

1. finish capturing the utterance
2. stop/release the live microphone stream
3. transcribe the captured audio with STT
4. let an accelerated STT provider release inference resources when it supports `release_for_inference()`
5. wait the configured 1.5 second handoff delay
6. wake/run the LLM or VLM
7. restart the microphone after the response-generation phase returns

This avoids unnecessarily keeping the live audio stream active while the model works, and places the handoff delay between STT and the LLM rather than before transcription.

The existing `faster-whisper` path remains a fallback. A Qualcomm/Arduino-accelerated Whisper provider is intentionally not hard-coded until a stable documented API has been verified on the physical VENTUNO software image.

## Physical validation boundary

CI validates architecture, parsing, fail-closed policies, streaming, routing and state transitions. It cannot validate:
- Hexagon NPU performance
- QAIRT model compatibility
- GenieX long-duration stability
- real microphone/STT latency
- VLM camera quality
- STM32 Router timing
- temperature, power or throttling
- actual peripheral behavior

Those checks begin only when VENTUNO Q hardware is available.


## Local LLM fallback

MyAI now has an optional local fallback wrapper around the selected LLM provider.

The fallback is deliberately disabled in both the default and VENTUNO profiles until a reserve model has been validated on physical hardware.

When enabled:
- normal requests use the configured primary model
- if the primary request fails before producing output, MyAI can retry with the configured local reserve model
- streaming only falls back if the primary backend fails before the first emitted token
- if a primary stream fails after output has started, MyAI stops instead of mixing two model responses
- every completed response carries internal runtime metadata identifying whether the primary or fallback backend was used

The intended VENTUNO use is a high-performance QAIRT/NPU primary model with a smaller, separately validated local GenieX model as emergency fallback. The exact reserve model must be chosen from the models that are actually compatible with the board and validated in the physical test phase.


## ASR provider separation

MyAI now supports separate primary and backup STT providers.

Current VENTUNO profile:
- primary STT: `faster_whisper` until a documented accelerated provider is verified
- backup STT provider: `faster_whisper`
- model release before LLM/VLM: enabled on VENTUNO, disabled in the Windows default profile

The intended physical-board configuration is:
- primary: the verified Qualcomm/Arduino accelerated Whisper path
- backup: `faster-whisper`
- same MyAI voice pipeline and safety/consensus logic regardless of provider

The official VENTUNO Q local assistant uses Whisper Small (quantized) through the Arduino App Lab ASR Brick. MyAI does not assume a private or undocumented Brick API.

## Expanded preflight

The read-only VENTUNO preflight now also checks:
- `geniex --version`
- `geniex model list`
- whether the configured primary Qwen model appears in the chipset-compatible model catalogue

A successfully executed model list that does not contain the configured model is a blocking failure. A CLI/catalogue error is reported as a warning rather than being treated as proof of incompatibility.


## 72-hour stability harness

A hardware stability harness is prepared but is not run in CI:

```bash
python3 scripts/ventuno_stability_test.py --hours 72
```

Before inference begins, the script runs the VENTUNO preflight unless `--skip-preflight` is explicitly supplied for debugging.

Each iteration records one JSON object in:

```text
runtime/ventuno_stability.jsonl
```

The record includes:
- success/failure
- first emitted LLM chunk latency
- total response duration
- response character/chunk counts
- primary/fallback runtime metadata
- CPU usage
- RAM usage
- disk free space
- temperatures reported through psutil when available

The default interval is 60 seconds. The prompt is intentionally harmless and deterministic.

The stability harness does not enable STM32 RPC writes, GPIO, relays or motors. Hardware actuation must be tested separately after the MCU safety boundary and write allowlists have been approved.


## GenieX supervisor / watchdog

MyAI has a separate GenieX supervisor that checks the OpenAI-compatible readiness endpoint:

```text
GET http://127.0.0.1:18181/v1/models
```

This check does not generate tokens.

Run one check:

```bash
python3 scripts/geniex_watchdog.py --once
```

Run continuously:

```bash
python3 scripts/geniex_watchdog.py
```

The VENTUNO profile currently enables health monitoring but keeps automatic restart disabled.

Safe default policy:

```json
{
  "enabled": true,
  "failure_threshold": 3,
  "restart_enabled": false,
  "restart_command": [],
  "restart_cooldown_seconds": 60,
  "max_restart_attempts": 3
}
```

Automatic restart must not be enabled until the physical board's actual GenieX service manager has been verified.

When restart is eventually enabled:
- the command is stored as an argument list, never shell text
- no `shell=True` execution is used
- restart waits for the configured consecutive-failure threshold
- a cooldown prevents restart loops
- a maximum attempt count prevents endless recovery cycling
- watchdog events are written to `runtime/geniex_watchdog.jsonl`

MyAI also exposes a read-only `geniex_status` tool. Natural-language tools do not expose any GenieX restart action.

The exact production restart command is intentionally blank today. Do not assume a systemd service name until the real VENTUNO installation has been inspected.
