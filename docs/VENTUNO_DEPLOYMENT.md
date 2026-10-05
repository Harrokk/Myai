# VENTUNO Q deployment

This deployment layer is prepared for the physical Arduino VENTUNO Q but does not install or enable services automatically.

## 1. Validate configuration

Interactive/development validation:

```bash
python3 scripts/validate_config.py --ventuno
```

The validator blocks unsafe contradictions such as:
- unknown LLM/vision providers
- non-local GenieX endpoint for the VENTUNO profile
- enabled LLM fallback without a reserve model
- GenieX restart enabled without an explicit argument-list command
- STM32 write RPC enabled without RPC and a non-empty write allowlist
- enabled vision without a model

Warnings are reported separately from blocking errors.

## 2. Preflight on the physical board

```bash
python3 scripts/ventuno_preflight.py
```

The headless runtime requires this preflight by default on the VENTUNO profile.

## 3. Headless runtime

Development/manual launch:

```bash
bash scripts/start_ventuno_headless.sh
```

This runs `scripts/ventuno_runtime.py`, not the interactive `mail.py`.

The headless runtime:
- validates configuration
- optionally requires VENTUNO preflight
- initializes MyAI memory/core
- starts hardware monitoring if enabled
- starts trusted-terminal handoff if enabled
- starts handsfree voice only when both voice and handsfree are explicitly enabled
- writes a heartbeat to `runtime/myai_runtime.json`
- shuts down components on SIGTERM/SIGINT

The current VENTUNO profile still leaves physical voice/RPC paths disabled until hardware validation.

## 4. Generate systemd units

Run on the actual VENTUNO installation:

```bash
python3 scripts/generate_ventuno_systemd.py
```

Generated files are written under:

```text
runtime/systemd/
```

The generator never writes to `/etc/systemd/system`, never invokes `systemctl`, and never enables a service.

Generated units:
- `myai-ventuno.service`
- `myai-geniex-watchdog.service`
- `myai-ventuno.target`

Both services run the config validator before startup.

Crash recovery is intentionally bounded:
- `Restart=on-failure`
- `RestartSec=5`
- `StartLimitIntervalSec=300`
- `StartLimitBurst=5`

This prevents an unlimited fast restart loop.

The generated services also use:
- `NoNewPrivileges=true`
- `UMask=0077`
- explicit project/profile paths
- the Python interpreter detected when the generator is run

## 5. Inspect before installation

Inspect every generated unit on the physical board before copying it to systemd.

Only after the actual VENTUNO user, paths, Python environment, GenieX installation and device permissions have been verified should the generated files be installed/activated manually.

The exact GenieX service dependency is intentionally not guessed today because the real GenieX installation/service manager has not yet been observed.

## 6. Logs and runtime state

JSONL logs are bounded and rotate automatically.

Defaults:
- maximum active JSONL size: 5,000,000 bytes
- backups: 5

This applies to the prepared GenieX watchdog and 72-hour stability logs.

Important runtime files:
- `runtime/myai_runtime.json` — headless runtime heartbeat
- `runtime/geniex_health.json` — current GenieX watchdog state
- `runtime/myai_health.json` — current combined MyAI health state
- `runtime/geniex_watchdog.jsonl` — watchdog history
- `runtime/ventuno_stability.jsonl` — stability-test history

## Safety boundary

Deployment preparation does not:
- enable STM32 writes
- enable GPIO/motor actions
- enable GenieX automatic restart
- choose/enable the LLM fallback model
- install systemd files
- run `systemctl`
- pretend physical hardware validation has occurred
