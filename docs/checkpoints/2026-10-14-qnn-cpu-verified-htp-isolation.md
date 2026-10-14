# MyAI checkpoint — riktig Qualcomm QNN CPU-verifiering på VENTUNO

**Datum:** 2026-10-14
**Senaste kodgren:** `dev/ventuno-qnn-static-loader-audit-20261014`
**Draft PR:** [#153](https://github.com/Harrokk/Myai/pull/153), stackad på [#152](https://github.com/Harrokk/Myai/pull/152) och föregående utkast.
**Live-installation:** INGEN ÄNDRING. Ingen main-merge, tjänstomstart, kernel/driver-ändring, omkoppling, automatiskt selfdev-beslut eller installation av QNN-verktyg.
**Ljud:** USB-ljudkortet är avsiktligt inte anslutet och lämnas helt utan tester eller felsökning tills användaren kopplar in det.

## Bakgrund, genomfört tidigare denna dag

- Riktig VENTUNO Q ARM64 har QAIRT och FastRPC/HTP-bibliotek tillgängliga, QNN/GenieX-processer och modeller installerade. Vid live-kontroll av GenieX fanns dock ingen samtidig HTP mmap + secure FastRPC FD: `no_go_backend_unverified`, ingen HTTP-inferens skickades.
- Den lilla syntetiska 8×8-modellen är **16 004 byte** DLC, exakt kontrollerad via SHA-256. Den använder 64 byte quantized UFXP8-indata och hade tidigare verifierats på separat x86 Qualcomm CPU-backend.
- Två separat explicit begränsade HTP-försök på riktig VENTUNO Q gav båda **nonzero** från `qnn-net-run` efter **0,039 respektive 0,044 sekunder**, ingen utdata och ingen verifierad NPU-inferens; det andra hade `ADSP_LIBRARY_PATH` mot existerande V75 Skel. Ingen av körningarna ändrade produktion. Upprepa inte HTP-försök på chans.

## PR #153: ny verklig evidens

### 1. ELF shared library dependency check (skrivskyddad)

- En första readelf-baserad kontroll [run 38580612603](https://github.com/Harrokk/Myai/actions/runs/38580612603) var ofullständig därför att `readelf` inte är installerat hos runnern.
- `scripts/ventuno_elf64_dynamic_reader.py` implementerar en begränsad ELF64/AArch64-analys i **ren Python** för att läsa `DT_NEEDED` från ELF-header/sektioner/dynamisk strängtabell. Ingen ELF-körning, `ldd` eller extra paket behövs.
- Riktig [run 38581446832](https://github.com/Harrokk/Myai/actions/runs/38581446832) kunde därefter läsa dynamiska beroenden för `qnn-net-run`, `libQnnHtp.so`, `libQnnHtpV75Stub.so` och `libQnnModelDlc.so`.
- Inga direkt NEEDED-bibliotek saknades i samplade standard/vendor-mappar. `libQnnHtpV75Stub.so` behöver bl.a. `libcdsprpc.so`, som identifierades. Vissa poster har ELF RUNPATH/RPATH. Dessa fynd bevisar **inte** att alla dynamiska `dlopen`-beroenden går att ladda, att loadern hittar rätt ABI-version eller att graph/HTP init fungerar.

### 2. QNN-programmet startar med befintliga resursgränser (ingen inferens)

- Riktig [run 38582071726](https://github.com/Harrokk/Myai/actions/runs/38582071726) körde endast `qnn-net-run --help` med samma sanerade miljö både med och utan de tidigare extra RLIMIT_AS/CPU/FSIZE/NOFILE-gränserna.
- **Med begränsningar:** exit zero, 0,029 s. **Utan begränsningar:** exit zero, 0,036 s.
- Den generella programstarten fungerar i begränsad miljö. Detta utesluter inte att en HTP-modell behöver andra mmaps eller uppstartskonfiguration.

### 3. VIKTIGT: syntetisk Qualcomm CPU-inferens lyckades på verkliga VENTUNO

- Riktig [run 38582751317](https://github.com/Harrokk/Myai/actions/runs/38582751317) utförde en enda opt-in-testkörning med `qnn-net-run` plus `libQnnCpu.so` och `libQnnModelDlc.so`. Den använde **precis samma syntetiska DLC (16 004 B) och 64 byte UFXP8-input** som de misslyckade HTP-försöken.
- **CPU-baserad QNN-inferens lyckades på VENTUNO:** en utdatafil med 64 byte och icke-nollvärden skapades. Utdata-SHA-256 matchade **EXAKT** samma tidigare verifierade x86 QNN CPU-resultat: `9f776aec98d9e12d5a33bb91fadcb8d6560293cc3e0d816445be6e9d05928174`.
- Subprocessens totala körtid: **0,128 sekunder**. Detta är en minimal 8×8 CPU-beräkning, INTE MyAI/GenieX svarstid, INTE Qwen-LLM prestanda och INTE NPU/HTP-inferens.
- Ingen HTP-backend initierades, inget USB-ljud, inga personliga indata, ingen extra stor språkmodell, ingen ändring av live Geniex/MyAI.
- CPU-körningen var begränsad till 1 verifierat test, minst 8 GiB fritt minne, max 20s child timeout, max 3 GiB virtuell adressrymd, 15s CPU-tid, 2 MiB per utfil, 128 FD och tillfälligt privat RUNNER_TEMP.
- Samtliga tester skrevs endast till development branch/temporär runner checkout. Inget uppdaterades i aktiv installation.

## Slutsats

**En konkret, tidigare osäker del av MyAI-plattformen är nu bevisad:** Det finns en fungerande, reproducerbar Qualcomm QNN-modellkörning på den riktiga VENTUNO Q-enheten med den egna syntetiska modellen på CPU, inte bara biblioteksnärvaro eller simulering.

**NPU är fortfarande blockerad.** De två tidigare HTP-försöken misslyckades så snabbt att någon NPU-inferens inte kan bekräftas. Resultaten pekar mot HTP-specifik drivrutin/runtime-konfiguration, kontext-/operator-kompatibilitet eller ytterligare dynamic-load-beroenden snarare än att hela DLC/indata/testmodell/CLI-kedjan är felaktig. Exakt orsak har ännu inte bevisats.

## Kod, workflow och verifiering

- `scripts/ventuno_qnn_static_loader_probe.py` och `scripts/ventuno_elf64_dynamic_reader.py` samt regressionsfiler.
- `scripts/ventuno_qnn_help_limit_preflight.py`: ingen modell- eller NPU-körning.
- `scripts/ventuno_qnn_cpu_reference_once.py`: en syntetisk **CPU**-exekvering, ingen HTP.
- Alla separata GitHub-workflows riktas till befintlig self-hosted VENTUNO-runner och läser endast rätt källkod i tillfällig Git checkout.
- [Full ARM64 CI 38582751221](https://github.com/Harrokk/Myai/actions/runs/38582751221): **1831 passed, 14 skipped**, static privacy/source audit **PASS, 0 blockerande**, med en tidigare dokumenterad test-helper `exec`-flagga för manuell kontroll och 495 spårade filer i den committen.
- Separata hosted x86-ONNX och crypto-körningar har redan verifierat valfria testfall som hoppas över på ARM. Denna PR ger inga nya beroenden till aktiv VENTUNO MyAI.
- Den dokumenterade GitHub Support-purge av gammal cache för känsliga historiska refs, [PR #110](https://github.com/Harrokk/Myai/pull/110), är fortfarande inte bekräftad. Ingen merge före lösning och oberoende granskning.

## Nästa säkra utvecklingssteg

1. Överväg en särskilt begränsad **errorkategori-only** insamling från en verifierad QNN HTP-start under ett separat granskad engångstest. Undvik öppna stderr-loggar med vägar, hemligheter, serie-/enhets-ID och användardata. Kör inte nya HTP-försök utan att först verifiera en säker felklassificering och resursgränser.
2. Undersök HTP v75 backend config/operatorkompatibilitet på separat SDK-host utifrån den **exakt verifierade 16 004 B DLC:n**, i stället för att prova andra stora modeller.
3. Parallellt: fortsätt MyAI-moduler och tjänstekontroller utan att röra saknat USB-ljudkort.
4. Verifiera verklig användarupplevelse först när skilda end-to-end krav uppfyllts. Någon färdig MyAI-röstupplevelse är inte verifierad av CPU-benchmarken.
