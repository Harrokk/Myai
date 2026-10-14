# MyAI checkpoint – HTP-initiering och FastRPC-behörigheter på verkliga VENTUNO Q

**Datum:** 2026-10-14
**Utvecklingsgren:** `dev/ventuno-fastrpc-access-readonly-20261014`
**Föregående granskade PR:** [#153](https://github.com/Harrokk/Myai/pull/153)
**Driftsättning:** Ingen. Alla nya komponenter är offline-/GitHub-runnerdiagnostik; ingen produktionskod, systemd-enhet, ägare, grupp, udev-regel, drivrutin, QNN-installation eller automatisk selfdev promotion har ändrats. USB-ljudkortet är avsiktligt inte inkopplat och får inte felsökas.

## Tidigare fastställda faktiska värden

- Tiny DLC: exakt SHA256-validerad **16 004 byte**, 64 byte syntetisk UFXP8-indata, QAIRT 2.45.
- Riktig VENTUNO ARM64 CPU-backend: `qnn-net-run` + `libQnnCpu.so` körde modellen korrekt. En enda 64-byte råutdata matchade exakt samma SHA256 som tidigare separat x86-QNN CPU-referens; **0,128 sekunder** subprocessens totala tid, [run 38582751317](https://github.com/Harrokk/Myai/actions/runs/38582751317).
- Två tidigare HTP-v75-försök på samma riktiga kort, med och utan explicit ADSP_LIBRARY_PATH, misslyckades med `qnn-net-run` nonzero på 0,039 respektive 0,044 sekunder. Ingen NPU-inferens verifierad.
- Statisk ELF-läsning i Python på riktig VENTUNO fann alla direkta `DT_NEEDED` i samplade SDK-/systemkataloger. Detta täcker inte dynamiska `dlopen`-beroenden och bevisar inte att HTP startar.
- QNN `--help` startar med och utan tidigare RLIMIT-gränser, vilket utesluter inte HTP-specifikt minnes-/DSP-behov.

## Nya faktiska kontroller

### 1. FastRPC-nodrättigheter, utan att öppna enheten

[GitHub-run #38584985843](https://github.com/Harrokk/Myai/actions/runs/38584985843), SUCCESS.

- Enheten för vanlig CDSP FastRPC fanns och `os.access(..., effective_ids=True)` rapporterade **läsbar och skrivbar** för runnern.
- `/dev/fastrpc-cdsp-secure` fanns och rapporterades **läsbar men inte skrivbar** för samma runneridentitet.
- 3 ytterligare FastRPC-/adsprpc-noder var synliga. **Inga noder öppnades**. Enhetsnamn, UID/GID, MAC/IP eller andra personliga miljövärden exporterades inte.
- AppArmor är aktivt på värden, SELinux enforce-flagga ej aktiv, `qnn-platform-validator` och `qnn-net-run` finns på PATH. Om AppArmor begränsar exakt QNN-processen är **inte** undersökt.
- Read/Write-rättigheter via metadata är inte samma sak som faktiskt lyckat kernel-open. Det kan också finnas särskilda ACL, capabilities eller drivrutinsspecifika regler.

### 2. En enda ytterligare, kategori-filtrerad HTP-diagnostik

[GitHub-run #38585894311](https://github.com/Harrokk/Myai/actions/runs/38585894311), SUCCESS som **diagnostikworkflow**, men QNN-inferensen gav **nonzero**.

- Samma verifierade lilla DLC + indata som föregående HTP-test.
- Fortfarande minst 8 GiB ledigt, kontroll att GenieX inte höll öppen säker FastRPC FD, max 30 sekunder för QNN-child, RLIMIT_AS 4 GiB, max 25 CPU-sekunder, max 2 MiB per utfil, separat privat RUNNER_TEMP-katalog. Ingen andra LLM, inga tjänstomstarter eller produktionsändringar.
- Skrivning av vendor stdout/stderr skedde **endast** i temporära privata filer; efter körningen behandlade `scripts/ventuno_qnn_error_categories.py` första max 16 KiB per ström och exporterade **bara** vitlistade kategorier, aldrig rå text/paths. Filerna försvann vid kontextens cleanup.
- Resultat: `status=qnn_htp_cli_nonzero`, **0,052 sekunder**, `error_categories=[backend_initialization_failure]`, 332 stdout-bytes och 23 stderr-bytes samplade, inga strömmar trunkerade.
- **Ingen HTP/NPU-inferens verifierad**. Kategorin visar att initieringen misslyckas; den anger inte ensam vilken konkret underliggande rättighetsregel eller backend-op som utlöste felet.

### 3. Jämför säker FastRPC-rättighet för runner och aktiv GenieX

[GitHub-run #38586363106](https://github.com/Harrokk/Myai/actions/runs/38586363106), SUCCESS.

- Verifierade systemd MainPID och exakt 1 aktiv GenieX-process, /proc/status för processens FSUID/FSGID och grupper, men inga PID/UID/GID-värden publicerades.
- **GenieX har samma FSUID som runnern**, inte root; ingen av dem har skrivbehörighet till säker CDSP-enhet enligt klassiska Unix-mode-bitarna. Runnern kan läsa den, inte skriva.
- Inga enheter öppnades, processer pausades eller drivrutiner ändrades. Resultatet är **DAC-modell**, inte faktisk open-call/ACL/MAC-kontroll eller bevis för att backend verkligen öppnar noden med O_RDWR.

## Slutsats och osäkerhetsgräns

**Starkare HTP-specifik hypotes:** En säker DSP/FastRPC-uppkoppling kräver en behörighet som nuvarande MyAI/GenieX/runner-identitet saknar, vilket skulle kunna ge omedelbar `backend_initialization_failure`. Denna hypotes är förenlig med metadata + kategoriserad backenduppstart, men är **ännu inte slutbevisad**. NPU-exekvering kan därför inte markeras lyckad.

Den aktiva GenieX-processen har tidigare vid annan tidpunkt varit observerad med libQnnHtp + secure FastRPC FD; det faktumet och aktuella DAC-rättigheter ska inte blandas ihop som samtidiga mätningar. Behörigheter, rätt säker/icke-säker PD-typ, ACL, AppArmor och DSP firmware kan spela roll.

**Säker nästa åtgärd:** ingen automatisk `sudo chmod`, `chown`, gruppändring eller udev-modifikation. Bedöm först Qualcomms/Arduino dokumenterade CDSP policy för exakt kortets firmware och hur QNN HTP-processen ska få tillgång (säker kontra icke-säker nod, eventuell udev/systemd-enhet, AppArmor). Utför en separat kontrollerad administrativ riskgranskning och rollback-plan före någon privilegieförändring. Fortsatt felsökning via läsmetadata och SDK-dokumentation kräver inte fysisk användarnärvaro.

## Kod som lades till

- `scripts/ventuno_fastrpc_access_readonly.py`: FastRPC char-device metadata och `os.access` via effektiv UID (utan open); testfil.
- `scripts/ventuno_qnn_error_categories.py`: vitlista för standardiserade QNN-felkategorier; regressioner mot hemligheter/filvägar och max bytes.
- Befintliga `scripts/ventuno_tiny_qnn_htp_once.py` har fått **extra opt-in** för kategori-filtrerad, temporär stderr/stdout-insamling; råfel exporteras aldrig, QNN-launch är fortfarande begränsad till separata engångs-workflows.
- `scripts/ventuno_geniex_fastrpc_dac_compare.py`: read-only /proc/status jämförelse av active GenieX FSUID/FSGID och klassiska POSIX-mode-bitar för secure CDSP; testfil.
- Isolerade GitHub Actions-workflows för var och en av de verkliga diagnostiska kontrollerna.
- Ingen produktionsintegration och ingen merge till main. GitHub Support-purge av historiska känsliga objekt i [PR #110](https://github.com/Harrokk/Myai/pull/110) är fortfarande en separat releaseblocker.

## Arbetsprioritet nästa gång
1. Verifiera vendor-specifik secure/nonsecure DSP/FastRPC policy på exakt Arduino VENTUNO / Qualcomm Dragonwing-plattform.
2. Om det behövs, bygg **en offline policy/rollback-checklista** för en eventuell framtida, uttryckligt godkänd serviceidentitets-/udev-/ACL-ändring. Använd inte root-privilegier förrän planen granskats.
3. Fortsätt MyAI:s övriga moduler utan USB-ljud, och använd runnern för skrivskyddad live-kontroll när det hjälper. Ingen blind QNN HTP retry.
