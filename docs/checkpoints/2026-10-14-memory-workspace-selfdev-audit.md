# MyAI – obemannad minnes-, fil- och rollback-granskning
Datum: 2026-10-14

## Syfte och förutsättningar
Användaren bad att fortsätta utan att vara vid VENTUNO eller Windows-datorn. Arbetet ska genomföras via GitHub Actions i isolerad test-checkout. Inga produktionsändringar eller hårdvaruingrepp är godkända.

## Nytt arbete i detta pass
1. **Minnesdatabasens dubblettkontroll:** `MemoryStore.save_if_new()` hade två separata steg (SELECT och INSERT). Nu atomisk SQLite-transaction med `BEGIN IMMEDIATE` för att undvika samtidiga dubbla aktiva minnen. Två nya regressionstester inklusive 8 parallella anrop.
2. **Workspace-filernas temporära filhantering:** Tidigare förutsägbar `<name>.tmp` skapad med `Path.write_text()` kunde följa förplacerad symlänk till annan plats. Ny exklusivt skapad `tempfile.mkstemp` bredvid destination, med fsync, os.replace och slutlig bortstädning. Två regressionstester; det äldre felinjektionstestet uppdaterades så att det testar den nya atomiska `os.replace`-gränsen. Inledande CI misslyckades på det äldre testet (run 38526718352), korrigerad omkörning PASS.
3. **Selfdev promotion/rollback:** Promotionens `promotion.json` sparas nu atomiskt; misslyckad journalkommit återställer alla applicerade filer innan felet rapporteras. Före manuell rollback verifieras samtliga källkodsbackuper mot sina förväntade SHA-256-värden och journalens fillista kontrolleras innan någon fil ändras. Rollback-record skrivs atomiskt. Tre regressionstester visar utebliven journal, manipulerad backup och ofullständigt manifest.
4. **Samtidiga minnesgranskningar:** `MemoryStore.enqueue_review()` sökte befintlig granskningspost separat från sin INSERT. Nu atomisk `BEGIN IMMEDIATE`. Regressionstest med sex parallella anrop verifierar en och samma post.

## Verifierade CI-resultat
- Omkörning efter uppdaterad filfelinjektion: https://github.com/Harrokk/Myai/actions/runs/38526953632 — **1516 passed, 6 skipped**.
- Selfdev journal & rollback-integritet: https://github.com/Harrokk/Myai/actions/runs/38527229347 — **1519 passed, 6 skipped**.
- Parallell minnesgranskningskö: https://github.com/Harrokk/Myai/actions/runs/38527534274 — **1520 passed, 6 skipped**.
- Sex ARM64-skips är tidigare kända host-only ONNX/NumPy-tester. De sex ingår i 22/22 PASS på tillfällig GitHub-hostad x86 Linux-runner: https://github.com/Harrokk/Myai/actions/runs/38520039444.

## Draft PR-kedja, inte i produktion
- #112 kamera-negation, #113 repo-audit och säker CI, #114 BLE-RSSI fail-closed, #115 riskfyllda svenska röstkommandon och minneshemligheter, #116 watchdog, samtliga draft.
- #117: https://github.com/Harrokk/Myai/pull/117 — atomisk minnesdeduplicering + symlänkssäker filskrivning.
- #118: https://github.com/Harrokk/Myai/pull/118 — självutveckling: säker backup och felhantering vid promotion/rollback.
- #121: https://github.com/Harrokk/Myai/pull/121 — minnesgranskningskö klarar samtidiga förfrågningar.

Inga grenar automatiskt mergade, ingen kod installerad på `/home/arduino/MyAI`. Tester använde temporär CI-checkout, temporära SQLite-testdatabaser och filområden. Ingen användardatabas, mic, högtalare, kamera, BLE-parning eller skrivning till STM32.

## Kvarstående
- De nya säkerhetsfixarna är enbart granskade utvecklingsgrenar, inte aktuell körande MyAI.
- Självutvecklingens rollback har ännu ingen fullständigt verifierad crash/power-loss-journal genom alla möjliga strömavbrott; de nya testerna täcker hanterade Python-undantag och manipulerade backuper. En senare granskning kan testa idempotent rollback efter avbrott i statusjournal.
- Verklig Bluetooth-handoff, USB-Audio efter omstart, svensk ASR med flera naturliga röster, GPS, kamera, NPU och långvarig stabilitet kräver framtida lämplig hårdvarukontroll.
- Windows / Arduino App Lab adressproblem ska förbli uppskjutet enligt användaren.
- GitHub historikrensingens dangling/cached användarmemory behövs fortfarande Support purge, PR #110 blockerar main merge.

## Fortsättning
Läs denna checkpoint, kontrollera de senaste grengränserna och PR-kedjan innan ny utveckling. Kör först säkra isolerade tester och gör inga riskfyllda produktionsändringar.
