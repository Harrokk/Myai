# MyAI checkpoint — verklig VENTUNO Q hardware-inventering på distans

**Datum:** 2026-10-14
**Gren:** `dev/ventuno-readonly-hardware-20261014`
**PR:** [#150](https://github.com/Harrokk/Myai/pull/150), fortsatt draft och stackad på PR #149.
**Viktigt:** Den här omgången kördes direkt på **riktig VENTUNO Q ARM64** via self-hosted GitHub Actions-runner, inte en simulering. Användaren behövde inte fysisk närvaro.
**Drift:** Inga source writes, systemd/reboots, ljudinspelningar, wifi/Bluetooth-scans, deployment, auto-updater, hemligheter eller privata adresser. MyAI/GenieX produktion orörd.

## Senaste riktiga maskinmätning

Källa: [GitHub Actions read-only probe #38568994632](https://github.com/Harrokk/Myai/actions/runs/38568994632) – conclusion SUCCESS.

| Område | Faktiskt avläst |
|---|---|
| CPU | aarch64, 8 logiska CPU, samplade 845–2362 MHz |
| Linux kernel | 6.8.0-1084-qcom |
| Upptid | ca 9.9 timmar vid mätning |
| RAM | 14.93 GiB totalt, 13.67 GiB MemAvailable, 0 GiB swap |
| Rotlagring | 54.90 GiB totalt, 29.77 GiB tillgängligt |
| Temperatur | 48 thermal-zone sensorer, 34.4–38.0°C |
| Wi-Fi | 1 interface, link up |
| Ethernet | 1 interface registrerat (up/down ej mätt) |
| Bluetooth | 1 HCI adapter synlig (ingen ihopparning/skanning testad) |
| GitHub runner | active |
| MyAI | active enligt systemd unit-lista |
| GenieX | active enligt systemd unit-lista |
| USB-devices | 3 registrerade |
| USB Audio-class interface | 0 |
| ALSA sound cards | 1 totalt, 0 USB-backade |
| ALSA capture PCM | 1 |
| ALSA playback PCM | 2 |
| ALSA capture/playback device nodes | 1 capture, 2 playback |
| FastRPC device nodes | 5 |
| Remoteproc | 3 visible, 3 running |
| QNN HTP library | found in standard paths |
| QNN System library | found in standard paths |
| RPC libraries | found in standard paths |
| SNPE library | found in standard paths |
| GPU render device node | 1 |
| Generic /dev/accel or /dev/qaic | 0,0 (NOT proof NPU missing) |

### Tolkning och säkerhetsgränser

1. **USB-ljud återstår:** ingen USB Audio-class interface eller USB-ALSA-card. Ett icke-USB ALSA-kort och 1 capture-PCM är synligt. Gissa inte att ALSA `card0` är användarens USB-mikrofon. Kontrollera separat capture-enhetens källa, routing och hardware, utan att spela in omgivningens ljud utan tydlig avsikt.
2. **NPU-stacken verkar installerad:** FastRPC, 3 running remote processors, HTP/QNN/SNPE/RPC-bibliotek och GPU-render-node är faktiska on-board tecken. Det är INTE proof of successful QNN model inference, modellkompatibilitet eller responstid. Nästa test kan vara en kort, explicit avgränsad offline NPU-model-inference med known-safe, syntetisk data, om rätt verktyg/paket tillåter det utan att störa produktion.
3. **Tjänster är aktiva:** systemd active för MyAI/GenieX/runner, men säger inte att svenska ASR, högtalare, USB-mikrofon eller AI-modell fungerar end-to-end.
4. **Wi-Fi och BT:** Wi-Fi-link up, 1 Bluetooth HCI-adapter. Ingen mätning av Wi-Fi throughput/latency eller faktisk BT-parning.
5. **Temperaturer 34.4–38.0°C är ögonblicksvärden**, inte ett stresstest eller en garanti mot throttling vid inferens.
6. **Inga IP/MAC/SSID, USB-/Bluetooth-serials, ljudsamples, credentials eller personuppgifter** finns i diagnostic output. Scriptet använder endast allowlisted metrics och unit states; systemctl anrop läser tjänstelistan.
7. **Driftändringar:** Inga användare skapade, inga filer i aktivt MyAI/GenieX installerade, inga tjänster startade/stoppade/restartade. GitHub-script körs med `python -B` i runner-tempcheckout och driver inga privilegierade hårdvaruoperationer.

## Kod och verifiering
- `scripts/ventuno_readonly_probe.py`: signerad GitHub-branch, enkel Python-kod som exporterar endast privacy-filterad JSON.
- `.github/workflows/ventuno-readonly-hardware.yml`: read-only workflow på riktiga `[self-hosted,Linux,ARM64,ventuno-q]`, exakt git-commit till temporär checkout.
- `tests/test_ventuno_readonly_probe.py`: schematester och safe-parser-fixtures.
- Kod/test-körning: [GitHub Actions #38568994615](https://github.com/Harrokk/Myai/actions/runs/38568994615) – **1804 passed, 14 skipped**, source/privacy static audit **PASS, 0 blockers**. En äldre `exec`-test-helper är fortfarande noterad för manuell kodgranskning.
- Tidigare första hardware snapshot: [run #38568238997](https://github.com/Harrokk/Myai/actions/runs/38568238997) – SUCCESS.
- Denna checkpoint uppdaterar inte tidigare release-blocker: GitHub Support cache-purge för äldre känslig historik (PR #110) är inte bekräftad. PR #112–#150 i utvecklingskedjan ligger kvar som draft/unmerged.

## Nästa steg som kan göras över runnern utan fysisk närvaro
- Ingen automatisk mikrofoninspelning: verifiera först exakt vilken ALSA capture-PCM som finns, utan mikrofon/ambient sample. Använd syntetisk ljudkälla om ljudvägen ska testas funktionellt.
- NPU: read-only inventory av QNN-runtime-versioner, firmware status och kompatibla testverktyg, följt av explicit kort syntetiskt NPU-test i isolerad process *om* verktyg och rättigheter finns och testet kan avbrytas.
- Mät MyAI/GenieX service health och lokal latency enbart via dokumenterade read-only endpoints efter granskning; ingen live user prompt eller kamera-/ljudaktion utan avgränsning.
- Riktigt strömavbrott/eMMC recovery och fysisk kabel-/USB-kontaktkontroll kräver fortfarande faktisk fysisk åtkomst och får inte simuleras som verifierad.
