# MyAI – slutprotokoll för fjärrbaserad källkodsrevision
**Datum:** 2026-10-16  
**Omfattning:** Källkod, Git-spårade konfigurationer, statiska säkerhetsgrindar, DRAFT-integrationshistoria, modulär regressionssvit och endast skrivskyddad VENTUNO-metadata.  
**Beslut:** **KÄLLKODSKONTROLLER KAN AVSLUTAS NÄR EXAKT-SHA-CI BLIR GRÖNT. HELA HÅRDVARU-/DRIFTREVISIONEN ÄR INTE AVSLUTAD. DRIFTSÄTTNING: NO-GO.**

Det här protokollet är ett ärligt avslut av den fjärrbaserade delrevisionen, inte ett intyg om fullständigt säker produktionssystem. Det får inte omtolkas som ett godkännande att slå ihop DRAFT-grenar med `main`, installera i den aktiva tjänsten eller utföra inspelning/acceleratortest utan särskilt beslut. En grön CI-körning är inte likvärdig med en manuellt rad-för-rad-verifierad och funktionstestad produkt.

## Uppnådda kontroller, med exakta begränsningar

| Kontroll | Källkodsevidens | Vad den INTE bevisar |
| --- | --- | --- |
| Två separata helträdspass | `scripts/ventuno_deep_source_audit.py`: AST/syntax/verktygsdubbletter; subprocess/integritet/JSON/Actions/beroenden. Blockerare ger statuskod 2. | Full manuell rad-för-rad-inspektion, full testtäckning eller korrekt installerad applikation. |
| Alla Actions | `scripts/ventuno_workflow_release_review.py` inventerar alla Git-spårade Actions och känsliga startmöjligheter för kandidatgrenen och `main`; atypiska händelser spåras som osäkra. | Full YAML-expression-, återanvändbara actions-, nedladdad kod- eller skriptkallsgrafanalys. |
| Alla manuella Actions | 103/103 filnamn, varav 56 tidigare känsligordsträffar och 47 övriga, matchas mot låst revisionsmanifest. | Ett manuellt flöde är inte säkert att köra bara för att dess namn är inventerat. |
| Manuella Actions – innehåll | `scripts/ventuno_manual_workflow_source_identity.py` jämför Git-blob-identitet för alla 103 arbetflödesfiler med frusen revisionsbaseline; innehållsändring spärrar CI tills ny granskning. | Git SHA-1-objekt-ID är inte en signerad leveranskedjeattestation, och skyddar inte mot oförändrade men osäkra externa beroenden. |
| Effektfulla äldre jobb | 15 riktade Whisper/GenieX/Ollama/QNN/HTP-jobb har `if: false` på jobbnivå, och två användarnivåns systemtimerprov likaså, i DRAFT-kandidaten. Fyra gamla main-jobb har också arkiverats. | De historiska filerna i andra grenar blir inte automatiskt ofarliga; gamla workflow_dispatch-rättigheter är inte nytt operatörssamtycke. |
| Konfigurationsläge i källan | `config/profiles/ventuno_q.json`: `voice.enabled=false`, `voice.tts_enabled=false`, `ventuno.rpc_write_enabled=false`. | Konfigurationen som är laddad i den pågående produktionstjänstens minne. |
| VENTUNO-metadata | Skrivskyddad fysisk runnerkontroll i [PR #253](https://github.com/Harrokk/Myai/pull/253), [körning 38938734852](https://github.com/Harrokk/Myai/actions/runs/38938734852). Matchad startfil, förväntat kommando/PID, 2 ALSA-kort, 2 capture- och 3 playback-noder. | Tal kan spelas in/upp, live-STT går eller verklig tjänstekonfiguration motsvarar kandidatprofilen. |
| Installerade röstpaket | Samma metadata visar att de normala produktionsimporterna `faster_whisper`, `pyttsx3`, `sounddevice`, `webrtcvad` inte finns i installerad `.venv`. Isolerad staging från PR #247 lyckades i temporär miljö. | Att installerad normal röstapplikation är klar för drift; staging är inte en installation. |
| Integrationshistoria | Kandidatgrenen innehåller tidigare granskat `main`-ursprung och kompletterande DRAFT-korrigeringar; full testkörning utförs på varje rapporterad slut-SHA. | Ändringarna är godkända för sammanslagning, manuellt diffgranskade i sin helhet eller installerade i produktion. |
| Återställning och minne | Syntetiska subprocess-, SQLite-, Stop- och återställningsprov har körts genom den ordinarie testsamlingen. | Faktisk reboot, strömavbrott, frikopplade hjälpprocesser, ljud-WAV på disk eller oberoende rollback under belastning. |

## De tolv ursprungliga fynden – formell stängningsstatus

| Nr | Revisionsfynd | Källkodsåtgärd / granskat | Slutstatus |
| --- | --- | --- | --- |
| 1 | VENTUNO ARM64-röstberoenden | Hashad temporär native staging, PortAudio/eSpeak-test; aktiv normal venv saknar 4/4 paket | **FYSISK/INSTALLATION ÖPPEN** |
| 2 | Main/DRAFT-integration | Separat kandidatgren byggd och återkommande full source-only ARM64 CI | **MERGE-/RELEASE-GRANSKNING ÖPPEN** |
| 3 | Whisper Small minnes-/processisolering | Styrbar OFF-profil, processframing, timeout, Stop, syntetiska worker-tester | **NATIVE STT/LATENS ÖPPEN** |
| 4 | WAV-integritet, process/strömavbrott | Tidig tempfilstädning/felinjektion och tester | **STRÖMAVBROTT/PRIVAT DISK ÖPPEN** |
| 5 | Aktiva konfigurationsvärden | Skrivskyddad startproveniens; ingen sekretsexponering | **IN-PROCESS BEVIS ÖPPET** |
| 6 | Minnes-/SQLite-testisolering | Separata provkonfigurationer och syntetiska Stop/skrivspärrar | **LIVE WAL/WRITE-GRIND ÖPPEN** |
| 7 | QAIRT/NPU/HTP | Versions-, DLC-, vendor- och metadataanalyser, historiska NPU-jobb avstängda | **NPU NO-GO** |
| 8 | Processgrupper/recovery | Syntetisk subprocess-grupp/timeout och kontroll av timerjobbs karantän | **OBEROENDE FYSISK ROLLBACK ÖPPEN** |
| 9 | Reproducerbara beroenden | 28 rösthjul hashlåsta, tillfällig ARM64-staging verifierad | **HELA INSTALLATIONENS LOCK/SBOM ÖPPEN** |
| 10 | GitHub Actions-säkerhet | 103 manuella kända, 56 risktriggade, 15+2 aktiva historiska jobb avstängda, innehållsmanifest och regressionsgrind | **STATISK INVENTERING KLAR, INDIREKTA SKRIPT/BEHÖRIGHETER FÖR RELEASE EJ SLUTATTESTERADE** |
| 11 | USB-röstkedja och temperatur/svarstider | Ljudenhetsmetadata och syntetisk transkript→RAM-WAV | **MIKROFON/HÖGTALARE/LATENS ÖPPEN** |
| 12 | Övriga moduler | Namnkollisioner, syntax och tester av laddnings-/routingkontrakt | **AKTIV MODULVISA E2E-TESTER ÖPPNA** |

Det är **inte** korrekt att markera alla tolv fynd som fullt stängda. Kod- och källsäkerhetsdelen är långt framskriden, medan de installerade och fysiska beslutsgrindarna är bevisligen öppna.

## Fysisk slutkampanj – kräver separat överenskommelse, ingen automatisk aktivering

1. **Oberoende återställning och aktiv tjänst:** Operatör framför VENTUNO. Dokumentera godkänd exakt release-SHA, systemd ExecStart, laddad konfigurationsattestation, separat minnesdatabas/WAL, backup och fristående Stop/rollback. Verifiera att originaltjänst kan återfås och att runnern kan återansluta.
2. **Isolerad normal röstinstallation:** Besluta minimal hashad ARM64-venv, kontrollera PortAudio/eSpeak/native ABI och import av `faster_whisper`, `sounddevice`, `webrtcvad`, `pyttsx3`. Bevara aktiv produktion OFF.
3. **Kort samtyckt röstprov:** Endast efter nytt uttryckligt tillstånd på plats; upp till ett begränsat mikrofonklipp i testprofil; verifiera STT, svar, TTS via verklig högtalare, Stop under arbete, avvisad skrivning och säkert avslut med städning. Logga inte ljud eller privat transkript.
4. **Resurs- och återställningsprov:** RAM, p50/p95 svarstider, temperatur, processbarn, IPC, timeout, tvingat avbrott och verifierad test-WAL. Inga out-of-band-funktioner får antas fungerande utan prov.
5. **Separat NPU/HTP-beslut:** Kontrollera verklig QAIRT/driver/DLC/API-version, exklusiva acceleratorresurser och möjligheten att återställa även om HTP blir oåtkomlig. Kör bara en särskilt godkänd minimal testprofil med operatör på plats. Inget automatiskt nätverksjobb återaktiveras.
6. **Releaseprövning:** Fastställ release-SHA och dependency-SBOM, granska samtliga beroende-/workflow-action-referenser och hela diffen mot `main`; kör exakt release-SHA-tester igen. Först därefter övervägs merge och kontrollerad installation med bevisad rollback.

## CI-evidens och tolkning

- Ursprunglig tvåpassrevision: [PR #238](https://github.com/Harrokk/Myai/pull/238).
- Verifierat genomgångsläge: [PR #260](https://github.com/Harrokk/Myai/pull/260), [ARM64-körning 38949312824](https://github.com/Harrokk/Myai/actions/runs/38949312824), **3 199 godkända / 15 hoppade över** vid exakt `5d8ec1fe806ba7f73c441abb2114c8f0b9f390b6`.
- Den här nya DRAFT-grenen för slutprotokollet **kräver egen full ARM64 CI och separat exakt-SHA revisionsgrind**. Föräldergrens gröna körningar får inte tillskrivas den nya SHA:n.
- Alla källkodskontroller ger explicit `production_deployment_authorized=false` och `main_merge_authorized=false`. Uppföljning av fysiska grindar krävs innan en full driftrevision kan stängas.

**Beslut: Fjärrbaserad tvåpassig källkodsinventering och spärrkontroller kan arkiveras som separat genomförd revisionsfas när ny CI passerar. Hela revisionen är INTE avslutad och MyAI är INTE godkänd för drift.**
