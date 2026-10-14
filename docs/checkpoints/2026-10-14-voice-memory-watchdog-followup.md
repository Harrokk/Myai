# MyAI – obemannad kvalitets- och säkerhetsutveckling 2026-10-14

## Aktuell utvecklingskedja
- PR #112: negationsskydd för kamerakommandon. https://github.com/Harrokk/Myai/pull/112
- PR #113: fullständig källkodsbaserad 411-filskontroll, release-workflow read-only token, host-only ONNX-körning. https://github.com/Harrokk/Myai/pull/113
- PR #114: fail-closed Bluetooth-RSSI, ogiltiga gränsvärden och handoff-test. https://github.com/Harrokk/Myai/pull/114
- PR #115: nekande/icke-nekande högriskrösttranskript får inte automatiskt konsensus; felaktigt STT-konfidensvärde avvisas; formatigenkänning för hemliga token före långtidsminne. https://github.com/Harrokk/Myai/pull/115
- PR #116: robust GenieX watchdog och hälsorapport mot skadade counters, NaN/inf och framtida timestamps. https://github.com/Harrokk/Myai/pull/116
- Alla PR är draft och staplade med egna basgrenar; ingen är sammanslagen eller installerad i produktion.

## Verifiering i GitHub Actions
- Grundomgången PR #112: 1491 passed, 6 skipped.
- PR #114 Bluetooth: run 38523402237, 1498 passed, 6 skipped.
- PR #115 röst/minne: run 38525403795, 1504 passed, 6 skipped.
- PR #116 med watchdog routing och health status: run 38525888898, **1512 passed, 6 skipped**, success. Compile + full pytest i isolerad temp checkout på riktig VENTUNO ARM64.
- Sex valfria host-only tester kräver ONNX/NumPy som saknas i Ventuno:s CI-miljö; samtliga sex ingår i 22/22 godkända host-tester: run 38520039444 på isolerad GitHub-hostad x86 Linux-runner. Därför ska ARM64-skip inte betraktas som felsignal.
- Den separata statiska granskningen på VENTUNO, run 38519887631, gav 411 filer, 328/328 giltig Python-syntax, 46 workflows, två giltiga JSON-profiler och 0 blockerande statiska fynd. Den var inte ett fullständigt bevis för kodens beteende.

## Gränser / öppna risker
1. User postponed Windows/Arduino App Lab IP/mDNS troubleshooting. Gör inte den kontrollen utan att användaren vill.
2. Tidigare read-only USB-diagnos run 38508999336 visade att förväntat USB ALSA-ljudkort saknades efter reboot. Inget inspelnings- eller uppspelningstest får startas automatiskt.
3. Verklig röst-ASR med flera svenska talare, faktisk USB-mic/USB-speaker, Bluetooth-handoff, GPS, kamera, STM32, NPU-prestanda och 72-timmars stabilitet är inte bevisade av CI. Kräver lämplig fysisk/explicit auktorisering eller ett separat godkänt read-only underlag.
4. GitHub server-side dangling/cached memory.db historik kvarstår enligt blocker-PR #110: https://github.com/Harrokk/Myai/pull/110. Kräver GitHub Support eller uttryckligt riskacceptans före main merge.
5. Inget produktionssystem, modellinstallation, tjänstekonfiguration, mikrofon, kamera, Bluetooth-parning eller fysisk nätverksinställning ändrades av denna testserie.

## Nästa möjliga autonoma arbetspass
- Fortsätt testdriven säkerhetsgranskning av `core/memory_lifecycle.py` (konflikt, data-integritet, ersättning och gränser), `core/voice_pipeline.py` (överensstämmelse, confirmation, lågnivå-fel), samt `modules/files/workspace.py` / `core/selfdev_*` för race conditions, symlink/path traversals, avbrott och rollback.
- Prioritera verifierbar reproduktion, liten isolerad ändring, full ARM64 pytest, draft PR och checkpoint. Undvik att själv slå ihop PR:er i main eller installera dem i den aktiva tjänsten.

Checkpoint skapad från verifierade testjobb och specifika GitHub-utvecklingsgrenar; detta är ingen produktionsrelease.
