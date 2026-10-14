# MyAI – samlad obemannad säkerhets- och programkontroll

Datum: 2026-10-14
Projekt: Harrokk/Myai
Bas för granskning: dev/safety-capture-intent-20261014
Granskningsgren: dev/unattended-audit-20261014
Utrustning: riktig Arduino VENTUNO Q via GitHub Actions, samt isolerad GitHub-hostad x86 Linux-VM

## Omfattning och verifierade resultat

1. **Fullständig MyAI-enhetstestsvit på VENTUNO:** run 38520039362 – SUCCESS. **1491 passed, 6 skipped**. Körning från isolerad temporär checkout. Dessa sex avser utvecklarvärdens valfria `onnx`/ `numpy`-tester. Kodkompilering utfördes innan enhetstesterna.
2. **Helträdets statiska granskning på VENTUNO:** run 38519887631 – SUCCESS. **411 spårade filer**, **328/328 Pythonfiler parsade**, **46 GitHub-workflows**, **2/2 JSON-filer giltiga**, **149 testfiler**, **1362 testfunktioner**, **0 blockerande statiska fynd**. Detta är en källkodskontroll; den kan inte utesluta alla logiska buggar eller sårbarheter.
3. **De separat utelämnade ONNX-/NumPy-testerna på x86-värd:** run 38520039444 – SUCCESS, **22 passed, 0 skipped** i de tre relevanta testfilerna. Inkluderar samtliga sex som hoppades över på ARM64. Använde en tillfällig GitHub-hostad runner och venv med fixerade beroendeversioner, inte Ventuno eller användarens Windows-dator. Testerna validerar host-baserad ONNX/CPU-matematik, **inte** QAIRT/NPU-prestanda eller Qualcomm-konvertering.
4. **Rättighetsgranskning:** `.github/workflows/release-zip.yml` hade implicit standardrättighet för token; `permissions: contents: read` har nu lagts till i granskningsgrenen. Efter korrigeringen återstod **en** statisk flagga för manuell granskning: ett avsiktligt `exec()` i `tests/test_ventuno_whisper_base_swedish_comparison.py:202` som kör en projektdefinierad mätningskodsträng i testsyfte. Inga blockerande fynd.
5. **Äldre verklig read-only VENTUNO-kontroll:** run 38508914285 – 69 passed; MyAI och GenieX aktiva, konfigurationsflaggor fail-closed, Ollama inte startad. Ny statisk audit verifierade inte dessa runtime-fakta på nytt utöver service-check efter cleanup.
6. **Äldre live read-only nätverkskontroll:** run 38516851399 – fungerande Wi-Fi, IPv4 standardrutt, mDNS/Avahi, SSH, GitHub-runner, MyAI och GenieX. Inga nätverksadresser publicerade.
7. **Äldre live read-only USB-kontroll:** run 38508999336 – **tidigare USB ALSA-kort saknades**. Icke-USB card0 får inte automatiskt användas i stället. Inga ljudenheter öppnades.
8. **Svensk ASR:** jämförelsen run 38507835110 gav 0/4 exakta på en human inspelning för Tiny respektive Base under skilda dekoderinställningar; tidigare syntetiskt Piper Alma 8/8. Resultaten räcker inte för slutsats om verklig användar-ASR. Försök att hitta fler offentliga ljudklipp gav HTTP 429, ingen ny körning gjordes.
9. **Kameratolkning:** separat PR #112 innehåller fail-closed-kontroll för negationer och två regressionstester. Denna auditgrens 1491 godkända tester inkluderar dessa.
10. **Git-historik:** rewrite av publika branch-/tag-referenser redovisad som klar i HISTORY_CLEANUP.md men gamla dangling/cachade objekt finns kvar via direkt historisk SHA. GitHub Support-rensning fortfarande blockerare för main enligt PR #110. Ingen ny historikrewrite genomfördes.

## Ändringar som hålls avskilda från produktion

- PR #112: https://github.com/Harrokk/Myai/pull/112 (kamera-fail-closed)
- PR #113: https://github.com/Harrokk/Myai/pull/113 (statisk audit, workflow-rättigheter, host-ONNX och checkpoint)
- Ingen PR har automatiskt slagits ihop i main eller installerats i `/home/arduino/MyAI`.
- Inga inspelningar, högtalaruppspelningar, USB reset, Bluetooth-parningar, kameraaktiveringar, STM32-skrivningar, omstarter, bestående paketinstallationer eller ändringar av produktionskonfiguration genomfördes i dessa kontroller.

## Uppskjutna moment

- Windows/Arduino App Lab `invalid board address / invalid IP` felsöks vid senare tillfälle enligt användarens uttryckliga önskan.
- USB-kortets fysiska eller lokala ALSA-orsak måste klargöras innan verkligt rösttest.
- Verklig svensk flerpersons-ASR, handsfree och live ljud kräver fysisk närvaro och ny tydlig inspelnings-/uppspelningstillåtelse.
- Bluetooth-anslutning, GPS, kamera, NPU-inferens, STM32 och hårdvarustabilitet kan inte säkert funktionsverifieras enbart med de nu godkända icke-invasiva testen.
- GitHub Support-rensning av historiska cachade objekt kvarstår.

## Fortsättning

Börja med att läsa denna checkpoint och PR #112/#113. Behåll produktionsläget oförändrat och separera statiska / host-baserade testresultat från verkliga VENTUNO-hårdvarutester. Före huvudgrenens merge: bedöm beroende-PR:erna, GitHub-cache-frågan och kvarvarande hårdvarukontroller.
