# MyAI – första verkliga hårdvarutestet, steg 1, VENTUNO Q

**Datum:** 2026-10-22 cirka 15:54 UTC / 17:54 svensk sommartid (CEST).
**Fysisk enhet:** `ventuno-q`, Arduino VENTUNO Q, Linux ARM64, runner `arduino`.
**Status:** **Steg 1 metadata-baslinje godkänd; ljudsignal och NPU-inferens ej testade. Produktion NO-GO.**

## Kodlåsning och spårbarhet

- Orörlig **testkällkod:** `d28165c1cad81f8b4308ac7355a3fdfd81334986`, från DRAFT #349, tidigare verifierad på hostad ARM64 med 4 247 godkända tester och 7 överhoppade: https://github.com/Harrokk/Myai/actions/runs/39190171714.
- Körworkflowens egen instrumentation-SHA: `d0b085ad1ae424053fe8faf3c99f18978735769e`.
- **Fysiskt GitHub Actions-jobb:** https://github.com/Harrokk/Myai/actions/runs/39809127108 – SUCCESS. Samtliga steg slutförda.
- Exakt detached `git`-checkout av låst test-SHA i tillfällig och privat katalog; ren katalog verifierad. Inga installerade produktionsfiler kopierades över.
- Alla hårdvaruläsningar utfördes med befintliga read-only-moduler från den låsta koden; Python `-B`, separata tidsgränser, no `sudo`, ingen ändring av tjänster, inga öppna USB-ljudströmmar, ingen NPU-inferens.

## Faktiska fysiska baslinjemätningar

| Värde | Fysisk avläsning |
|---|---|
| Linux-arkitektur | `aarch64` |
| Linux-kärna | `6.8.0-1084-qcom` |
| Logiska CPU-kärnor | 8 |
| Samplade CPU-frekvenser | 8 kärnor, 1 574–2 362 MHz (översikt); separat idle-sampling 1 498–2 362 MHz |
| Temperatursensorer | 48 |
| Temperaturspann vid första sampling | 31,1–35,1 °C |
| Högsta temperatur vid idle-sampling | 35,0 °C |
| Totalt RAM | 14,93 GiB |
| Tillgängligt RAM | 13,35–13,36 GiB i två avläsningar |
| Root-lagring totalt | 54,9 GiB |
| Root-lagring tillgängligt | 29,06 GiB |
| Swap | 0 GiB |
| Drifttid vid prov | 204,7 timmar |
| Tjänster | `myai`, `geniex` och `github_runner` alla rapporterade **active** |
| Nätverksindikatorer | Wi-Fi gränssnitt 1, länk up 1; Bluetooth HCI 1; ethernet gränssnitt 1 |
| USB audio | 1 USB-ljudkort, totalt 2 capture-PCM och 3 playback-PCM, ALSA capture/playback `[1,0]` åtkomliga |
| NPU-metadata | 5 FastRPC-device nodes, 3 synliga / 3 igång remote processors, QNN HTP-, QNN System-, RPC- och SNPE-biblioteksindikatorer närvarande |
| Riktigt NPU-test | **INTE** utfört. NPU-cykler, inferenslatens, HTP-placering och exklusiv NPU-underhållsbehörighet ej verifierade. |

## Readiness-rapporter

`scripts.ventuno_usb_voice_dialog_readiness`:
- `status=ready-for-separate-consented-dialogue-test`
- `arm64=true`, `services_active=true`, `production_voice_disabled=true`
- `usb_capture_and_playback_1_0_accessible=true`
- `ram_available_mib=13671`, minimum `8192`
- `disk_available_mib=29753`, minimum `3072`
- `microphone_opened=false`, `speaker_opened=false`, `model_loaded=false`, `production_changed=false`.

`scripts.ventuno_big_test_readiness --board-metadata-only`:
- `status=metadata-completed-needs-operator-test`
- alla fem metadataunderlag närvarande,
- USB-röstmetadata, NPU-metadata, HTP-/profilmetadata och återställnings-dry-run-metadata gick att klassificera,
- `physical_audio_authorized=false`, `npu_cycles_measured=false`, `real_microphone_audio_tested_now=false`, `real_speaker_playback_tested_now=false`,
- `automatic_rollback_armed=false`, `human_operator_verification_still_required=true`.

Slutlig source- och produktionsprofilsspärr:
- `board-readonly-preflight-passed`
- exakt låst source verifierad,
- faktisk installerad röst-/skrivprofil kontrollerad och default-OFF.
- Endast **färsk metadata** kontrollerad, inte STT-kvalitet eller ljudsignal.

## Ofullständiga säkerhetskontroller

Det tidigare fysiska testet 2026-10-19 https://github.com/Harrokk/Myai/actions/runs/39215347361 rapporterade `blocked_local_runner_privilege_preflight`: separat härdad runner-UID, historiska åtkomster, isolerade DAC/ACL och runner group-rättigheter var **inte** godkända. Detta test den 22 oktober **ändrade eller installerade inte** sådan isolering. Källkods- och metadatatesternas PASS är därför **inte** produktionsgodkännande.

## Gräns till steg 2

Kräver ett *nytt uttryckligt användargodkännande för en kort ljudinspelning och låg högtalaruppspelning*, helst när användaren är fysiskt vid VENTUNO med fungerande stoppmöjlighet. Föreslagen sekvens:

1. Samma låsta kod-SHA och frisk USB `1:0` kontrolleras åter.
2. En enda kort svensk testfras spelas in med tidsgräns, utan persistenta mikrofondata eller bakgrundslyssning.
3. Taligenkänning granskas; stoppa om fel.
4. Ett kort lokalt MyAI-svar genereras och spelas upp med låg nivå.
5. Testresultatet saneras för att inte logga röstinspelningar, transkript eller persondata; mät endast status och ungefärlig latens.
6. Ingen automatisk upprepning vid fel. Ingen service-/konfigurationsändring, NPU-belastning, självmodifiering eller körrättighetsmigrering.

**NO-GO för produktion och autonoma uppdateringar kvarstår.** Detta dokument är ett bevis för ett **första verkligt fysiskt, icke-invasivt hårdvarutest**, inte ett genomfört tal-smoke-test.
