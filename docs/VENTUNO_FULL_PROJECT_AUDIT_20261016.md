# MyAI – tvåpassig helprojektsrevision inför fysisk VENTUNO-testning

**Datum:** 2026-10-16. **Bas:** PR #237 (`affb76a9e9d92be1890ab04bc917297326d6c65f`). Detta dokument och integritetskorrigeringarna ligger i separat DRAFT PR #238.

## Omfattning och bevisvärde

- Logikpass: alla Git-spårade filer, Python-AST/syntax, arkitektur, verktygsnamn, moduler, konfigurationsflöden, testinventering och utvecklingsgrensintegration.
- Säkerhets-/driftpass: subprocess/exec, privat data, filsystem, beroenden, skrivande verktyg, processreaping, systemd, self-hosted GitHub Actions, HTP/NPU och manuell rollback.
- Dessutom selektiv **manuell fördjupning i faktiska kodvägar** för core, voice, memory, tools, nätverk, USB, Bluetooth, Excel, CI och fysisk testkedja. Ett fullträdigt AST-pass är **inte** samma sak som manuell rad-för-rad-verifiering av vartenda kontrollflöde eller 100 % funktionell kodtäckning.

**Spårad källinventering:** minst 754 filer, 485 Pythonfiler med giltig syntax, cirka 228 testfiler, 56 statiskt upptäckta verktygsnamn utan namnkollisioner, 143 Actions-workflows (108 nämner self-hosted), 7 requirements-filer med 11 direkta krav utan hashlåsning. Åtta känsliga AST-anrop (1 produktions-Popen, 7 testanrop) har separat syntetisk granskning i PR #237.

## Prioriterad fyndmatris

| Nr | Allvar / tidpunkt | Bekräftat fynd | Fjärråtgärd / nästa grind |
|---|---|---|---|
| **1** | **P0 – innan ordinarie röstapp** | **0 av 4 ordinarie röstmoduler finns i installerad /home/arduino/MyAI/.venv** vid aktuell VENTUNO-kontroll: faster_whisper, sounddevice, webrtcvad och pyttsx3 saknas. Två ALSA-kort och capture/playback-enheter finns, men det gör inte Python-vägen körbar. | Versionslåst **separat staging-venv**, installationsbarhet/native ABI och beroendetester; installera inte okontrollerat i produktion. Nytt godkännande före faktisk ljudaktivitet. |
| **2** | **P0 – inför samlad install** | DRAFT och main divergerar: 1693 commits före respektive 10 efter från DRAFT-perspektiv. De 10 main-unika commitsen tillför fyra CI-workflows. Detta bevisar integrationsskuld, inte 1693 automatiska konflikter. | Skapa isolerad integrationskandidat och granska konflikter/förändringar från båda grenar. Kör om full ARM64-regression på exakt kandidat-SHA. |
| **3** | **P0 – röstminne och svarstider** | Effektiv VENTUNO-profil: Whisper Small, streamande LLM, stt_process_isolation_enabled false, stt_persistent_worker_enabled false. Oktoberproverna använde fristående Tiny/ALSA-skript. Den ordinarie voice_factory skapar därför FasterWhisperSTT i processen. | Separat explicit profil med bestämd modell, minnesgräns, säkerhets-/Stop-beteende och korrekt ljud-backend. Inget produktions-voice-ON än. |
| **4** | **P0 – personuppgifts-/ljudintegritet** | modules/voice/providers.py hade faktisk WAV-läcka: misslyckad temp-WAV-konstruktion kunde lämna privat ljud innan transcribe-finally; efter felaktig unlink kunde transkribering felaktigt lyckas. | **Korrigerat i DRAFT PR #238** med två felinjektionstester. Kvarstående risk: kill/strömavbrott kan fortfarande lämna disktemp; planera tmpfs eller in-memory PCM för ordinarie drift. |
| **5** | **P0 – processens verkliga inställningar** | core/config.py laddar via miljövariabeln MYAI_SETTINGS, annars config/settings.json. Tidigare kontroll av installerad OFF-profil visar inte att den aktiva systemd-processen laddade samma profil. | Kontrollera aktiv ExecStart/config-proveniens i en sanerad metadata-only check; exponera aldrig hela processenviron/nycklar. |
| **6** | **P0 – data i testmiljö** | core/config.py har memory.auto_save_enabled true som default; MyAICore använder SQLite under project_root. Om full assistent körs kan en testkonversation beröra vanligt långtidsminne. | Separat SQLite-testdatabas, isolerat runtime/WAL och uttryckligt minne/skrivning OFF under första kompletta ljudprovet. |
| **7** | **P0 – före tung NPU-körning** | Upstream optrace i GenieX kräver enligt befintlig källkod QAIRT 2.48+, medan tidigare installerad runtime-version/paritet var 2.46. Ingen säker direkt HTP per-operatorprofil är verifierad. NPU readiness och recovery-dryrun är medvetet NO-GO. | Vendor-kompatibel signerad tiny-modell, QAIRT-/DSP-version, isolerat testfönster, HTP profilverktyg och fysisk återställning. Absolut inget parallellt oauktoriserat HTP-prov. |
| **8** | **P0 – native-recovery** | core/voice_stt_process_group.py kan stoppa sin processgrupp, men inte garantera att frikopplade helpers/egna sessions/cgroups har stannat. Out-of-band recovery är ännu inte verifierad. | Fysisk operatör, process-/serviceattestation och testad rollback före exklusiv HTP-underhållskörning. |
| **9** | **P1 – reproducerbar installation** | deployment_lock.required är false i VENTUNO-profilen. 11 direkta requirements saknar hash och 9 är versionsintervall. Valfria Python-/native-paket behöver pinning och ABI-verifiering. | Produktionsoberoende paketinventering, exakt installationsmanifest och beslutad stagingpolicy, inte oövervakad pip-install på VENTUNO. |
| **10** | **P1 – workflow-säkerhet** | 143 workflows; 108 nämner self-hosted. Historiska push/workflow_dispatch-filer omfattar arecord/aplay, GenieX och enskilda HTP-anrop. Flera har committext-grind, andra separat dispatch. De är historiskt branchbundna och vi påstår **inte** att de körs nu. | Tillåten-lista för source-only och avaktivering/arkivering av äldre effektfulla workflows inför integration. Commitmeddelande är inte ett nytt fysiskt samtycke. |
| **11** | **P1 – fysisk kvalitet/prestanda** | USB-enheten finns på ALSA 1:0. Den ordinarie ljudstacken använder sounddevice/WebRTC/pyttsx3, inte samma adapter som engångs-arecord/eSpeak. Vilovärden för RAM/temperatur är inte STT/NPU-latensmätningar. | Beroende-/routingprov utan ljud först, därefter samtyckt 3-s STT, LLM/TTS, Stop, p50/p95, effekt och temperatur under riktig belastning. |
| **12** | **P2 – återstående modulutveckling** | 56 registrerade verktygsnamn och omfattande tester, men Excel, internet/prisjämförelse, BLE/trusted-terminal, GPS, kamera och selfdev har skilda beroenden/behörigheter. Modul-laddning fortsätter efter importfel. | Modulvis import-/ABI-/funktionsmatris och end-to-end-tester för de funktioner som ska aktiveras. Dessa ska förbli OFF under det första begränsade ljudtestet. |

## Särskilda arkitekturkontroller

**Verktyg:** core/tool_manager.py importerar alla modules och uppdaterar TOOLS-dictionary. Inga statiska dubbletter upptäcktes, men faktisk importerbarhet måste verifieras på målmaskinen. Det skyddade voice-dispatchflödet har preflight, live-granskning, durable marker och avbrotts-/utfallslogik; det äldre o-skyddade textflödet är en separat testyta.

**Lagring/röst:** Normal FasterWhisperSTT skriver temporärt WAV till disk. Den nya kodfixen reducerar vissa läckscenarier men kan inte ge strömavbrottssäker borttagning. Normal Pyttsx3TTS och native modeller har verkliga tråd-/cleanup-gränser som måste granskas under kontrollerad belastning. MyAICore:s testdatabas ska vara separat från permanent minne.

**Hårdvara:** modules/ventuno/platform, core/ventuno_rpc, firmware och GenieX har individuella runtime-gates; RPC-write är OFF. Att HTP/FastRPC/QAIRT-bibliotek kan inspekteras metadata-only bevisar inte att en liten modell körs på rätt NPU-operator eller att profileringsspår är giltiga.

**CI och integration:** Huvudgrenen innehåller fyra egna nyare CI-workflows; de måste bedömas vid en kombinerad testkandidat. Åtta statiska AST-flaggor ska behållas i rapporten även om deras isolerade tester lyckats. Grön Python-syntax och frånvaro av automatiskt blockerande signaturer är inte ett allmänt säkerhetscertifikat.

## Vad kan färdigställas utan fysisk närvaro?

1. **Omedelbart:** isolerad full röstprofil, hashad requirements/staging-venv och passiv verifiering av installerade bibliotek; sanerad config-proveniens; minnesdatabasisolering och WAV-temporary-policy.
2. **Sedan:** integrationskandidat för DRAFT + main med full konflikt- och CI-testning; källkodssäker workflow-allowlist, och slutlig release-SHA.
3. **Därefter fysisk användare på plats:** en kort explicit godkänd mikrofon → STT → LLM → TTS- och Stop-kedja med riktiga mätvärden.
4. **Separat fysiskt underhåll:** exklusiv HTP/NPU operatorprofilering endast efter signerad modell, compat, korrekt stopprocedur och verifierad oberoende återställning.

**Slutbedömning:** isolerad USB-ljudtestning är nära redo efter nytt uttryckligt samtycke, men den fullständiga MyAI-röstinstallationen är **inte** redo att aktiveras med nuvarande produktions-venv. Stora HTP/NPU-test är fortsatt **NO-GO**. Håll allt DRAFT; inga aktiva ljud- eller systemtjänständringar.
