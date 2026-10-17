# MyAI – rollback: binda verklig filersättning till verifierad före-hash (2026-10-17)

**Bas:** PR #300, SHA `b69cfe2b85ff3dd9b7ea50e333d3ae56e5fea684`. DRAFT, inga verkliga återställningar eller aktiva VENTUNO-ändringar utförda.

## Pass 1: dataflödesrevision

Alla tre återställningsvägar – felhantering under promotion, explicit `recover_interrupted` och normal manuell rollback – skickar redan en verifierad `expected_after`-ordlista till `_restore_from_backup`. Den innehåller den senast tillåtna SHA-256-versionen för varje fil som ska återställas. För nytillagda filer använde metoden redan denna hash innan eventuell radering, men för **befintliga filer** kördes `_atomic_copy(snapshot,target)` utan förväntat tidigare målhashvärde. `_atomic_copy` öppnar och skriver via säkra katalogbeskrivare, men utan `expected_old` kunde den ändå ersätta en fil vars innehåll en annan process ändrat **efter preflight**. Det är en konkret risk för att skriva över nyare användararbete trots att hela preflightkontrollen tidigare såg korrekt ut.

## Pass 2: åtgärd, tester och begränsningar

- För varje tidigare existerande fil måste `expected_after[relative]` vara exakt 64 gemena hextecken. En saknad, felaktig eller oåtkomlig hash leder till ett uttryckligt fel **innan** backup-snapshot återställs.
- `_restore_from_backup` anropar nu `_atomic_copy(backup,target,expected_old=expected,expected_source=info["sha256"])`. Källans förväntade hash kontrolleras igen från den öppnade snapshot-inoden. Omedelbart före `os.replace` kontrollerar `_atomic_copy` även den öppnade målfilens bytes via `_source_matches_before_replace` och vägrar ersätta en annan version.
- Denna kontroll gäller samtliga tre befintliga anropsvägar och använder redan verifierad journal-/planinformation, utan nya inställningar eller användarfrågor.
- Tre nya regressionstester: (1) extern kodändring *efter* full preflight men *före* faktisk backupkopiering förhindrar överskrivning; (2) saknad förväntad måldigest stoppar direkt återställning; (3) snapshoten ändras efter dess verifiering men före kopiering och avvisas av förväntad källdigest.
- Kompletta befintliga tester för normal rollback, redan återställda filer, avbrutna updates, manuell recovery, felkorrigering, privata backupkataloger och journal-HMAC ska passera på samma slut-SHA.

## Restrisker / NO-GO

- Linux `os.replace` har ingen atomär compare-and-swap mot just den inode som nyss jämfördes med `expected_old`. En privilegierad icke-samarbetande lokal process med katalogskrivrätt kan fortfarande byta mål **mellan sista hashkontrollen och rename**. OS-rättigheter, privata kataloger och en gemensam kodmutationspolicy krävs.
- Vid rollback av flera filer kan tidigare steg redan ha hunnit utföras när en senare fil blockerar. Ordningsföljd, journalens `rollback_prepared` och separat återhämtningsbarhet är viktigt men garanterar inte en atomisk flerfilstransaktion.
- Normal promotion och annan recoveryinventering behöver fortsatt audit; fysisk av/på-strömavbrottstestning, repo-wide filrevision, DNS/SSRF, beroenden, SBOM/licenser/nativ ABI och VENTUNO:s ljud/NPU återstår.
- Ingen merge/deployment/aktiv selfdev är godkänd. Alla ändringar DRAFT med source-only ARM64-test.

**Krav:** komplett ARM64-projektsvit på exakt den senaste head-commiten, inga fel.
