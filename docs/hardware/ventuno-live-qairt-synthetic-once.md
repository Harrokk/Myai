# VENTUNO — ett begränsat syntetiskt test av aktiv GenieX/QAIRT

Detta test körs på **riktig VENTUNO Q** via dess befintliga self-hosted GitHub-runner. USB-ljud och mikrofon lämnas helt utanför: inget USB-ljudkort är anslutet.

## Säkerhetsvillkor

Skriptet `scripts/ventuno_live_qairt_synthetic_once.py` kräver **alla** dessa villkor före den enda förfrågan:

- GenieX process-ID och processens /proc-bibliotek ska styrka mappad `libQnnHtp.so` och öppen `/dev/fastrpc-cdsp-secure`, via redan testade `ventuno_geniex_runtime_attestation.py`.
- Minst 3 GiB `MemAvailable`; om detta inte kan verifieras blir testet NO-GO.
- Redan körande GenieX vid `127.0.0.1:18181/v1` ska annonsera exakt en Qualcomm Qwen W4A16-modell. Ingen ytterligare modell startas, hämtas eller laddas.
- Ett separat uttryckligt workflow-miljövärde `MYAI_ALLOW_SYNTHETIC_GENIEX_REQUEST=yes` krävs. Annars ska skriptet göra NO-GO utan HTTP-inferens.
- Sänd högst **en** prompt: `Compute 7 + 5. Reply only with the integer result.` med `max_tokens=24`, `temperature=0`, `stream=false` och 30 sekunders HTTP-timeout.
- Logga aldrig modellens svar eller användarinformation. Endast tids- och tokenvärden, HTP/FastRPC-bakgrundsevidens och säkerhetsgränser redovisas; max 128 KiB HTTP-svar får läsas.
- Aldrig ändra unit state, systemd, produktionskataloger, kod, NPU-drivrutiner, ljudenheter, modellkontexter eller intern modellkonfiguration.
- Skriptet kör från en exakt GitHub-commit i `RUNNER_TEMP`. Test-workflow triggas endast vid skapandet/ändringen av den särskilda workflowfilen eller explicit genom dispatch, inte av dokumentationsuppdateringar.

## Viktig tolkning

Om testet får ett giltigt icke-tomt genererat svar medan **samma aktiva GenieX-process** har QNN HTP + FastRPC evidence visar detta faktisk inferens via den aktiva QAIRT/GenieX-runtimevägen och starkt stöd för att NPU-backenden används. Det är **inte** direkt uppmätta NPU-cykler, HTP-utilization, optrace, tensorutfall, minnesprofil eller prestanda för en separat syntetisk QNN-modell.

Om säkerhetsvillkor brister lämnas status `no_go_*` eller `synthetic_request_error`, utan försök att starta någon ny model/service. Även ett godkänt kort test är inte ett godkännande för parallella LLM-modellstarter eller för ändrad active service.

QAIRT-projektets tidigare mer omfattande plan finns i `docs/VENTUNO_QAIRT_PROFILING.md`.
