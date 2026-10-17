# MyAI – sessions-JSON: en enda stabil inode under läsning (2026-10-17)

**Bas:** verifierad DRAFT PR #308, SHA `13c4dad17de4f2dd9e369650ac7e233704ab6322`. Källkods- och testsändringar i GitHub; source-only ARM64 CI. Ingen aktiv selfdev, installerad VENTUNO eller main-merge berörs.

## Pass 1 – dataintegritet och observerad brist

`SelfDevWorkspace._read_session_record(filename)` läser `session.json` eller `verification.json`. Katalogen och slutfilen öppnas redan via no-follow-FD, vilket förhindrar att en symlänk byter sökvägsroten. Men den gamla läsningen `os.fstat(fd)` → `handle.read(limit+1)` validerade enbart **inledande** filtyp, hårdlänksantal och storleksgräns. Den kontrollerade inte om en annan process skrev, förkortade eller lade till hårdlänk **under själva läsningen**. Därmed kunde en läsning bestå av blandade bytes från olika sessionstillstånd eller en avklippt fil som fortfarande parsades, trots att den aldrig motsvarade en stabil journalversion.

## Pass 2 – begränsad kodändring

- Filen öppnas fortfarande relativt `_session_directory_fd()` med `O_RDONLY|O_NOFOLLOW|O_NONBLOCK`.
- Kontrollera `fstat` före läsning: vanlig fil, exakt en hårdlänk, max 4 MiB.
- Läs via `os.read` i högst 64 KiB per iteration, med explicit 4 MiB + 1-byte gräns; efter läsningen kontrolleras `fstat` igen. `st_dev`, `st_ino`, `st_size`, `st_mtime_ns`, `st_ctime_ns`, filtyp, hårdlänkar och **exakt läst byteantal** måste stämma med första observationen.
- Vid avvikelse avbryt med `RuntimeError("Selfdev-sessionsfilen ändrades under läsning.")` före JSON-dekodning och före kontroll av t.ex. `passed` i verifieringsresultatet.
- Behåll tidigare JSON-format, API, storleksgräns och kravet på JSON-objekt. Detta steg gör **inte** någon ändring av JSON-nyckelsemantik, så äldre välformade sessionsfiler fortsätter att läsas.
- Fyra nya regressionsprov: skriv samma antal andra bytes under läsningen, trunkera filen under läsningen, skapa ny hårdlänk under läsningen, samt byt den yttre sessionskatalogens alias efter att filbeskrivaren öppnats och säkerställ att de ursprungliga pinnade byten används.

## Fortfarande NO-GO

- En privilegierad lokal skribent kan efter kontrollen ändra filens inode eller ersätta namn i katalogen; detta är ingen atomisk transaktionsisolation. Svaret gäller endast ett **kontrollerat läst snapshot** under testade hotmodeller.
- Python `json.loads` accepterar fortfarande duplicerade fältnamn och icke-finita konstanter som NaN/Infinity; strikta JSON-regler och signerade verifieringsresultat är ett separat revisionsmoment.
- En process som kontrollerar hela användarkontot eller selfdev-sessionernas privata filsystem kan kringgå stora delar av samma-UID-kontrollerna. Verklig OS-isolation och proveniens måste verifieras före release.
- Komplett repo-/beroende-/SBOM-/licensrevision, fysisk VENTUNO-mätning, NPU/ljud och reella strömavbrotts-/rollbacktester återstår. Ingen aktiv installation, merge eller promotion.

**Grind:** fullständig ARM64 source-only CI på exakt sista PR-SHA.
