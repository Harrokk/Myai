# MyAI checkpoint — behörighetsgranskning, privat projektlås och säkrare backup-snapshot

Datum: 2026-10-14
Senaste utvecklingsgren: `dev/selfdev-backup-snapshot-20261014`
Baserad på föregående godkända draft PR #130.
Alla förbättringar är fortfarande i draft PRs. De är INTE mergade till main eller installerade i aktiv MyAI på VENTUNO.

## PR #131 – projektnivåns behörigheter
- URL: https://github.com/Harrokk/Myai/pull/131
- Branch: `dev/selfdev-lock-permission-guard-20261014`
- Commit: `13336c4da8c1f232c9aff4d651be4b4f6a31f07c`
- Full VENTUNO Q ARM64 suite: https://github.com/Harrokk/Myai/actions/runs/38543197796 – **1580 passed, 6 skipped**.
- Tvingar kontroll av att `runtime/` och `runtime/selfdev/` inte är symboliska länkar, är riktigt kataloginoder och på POSIX ägs av aktiv UID utan group/other write.
- Projektlåset `.promotion.lock` öppnas med NOFOLLOW och NONBLOCK där OS medger; fstat kräver riktig ensam fil, ägd av körande användare och privata rättigheter (0600) på POSIX. Filtyper som hårdlänkar och öppna låsfiler nekas.
- Samma privatkatalogkontroll används före journalens HMAC-nyckel. Nya per-promotion backupkataloger skapas med mode 0700.
- Fem nya tester: world-writable lås, hardlinked lås, symlink i runtime-förälder, privat rollbackkatalog, group-writable metadata.

## PR #132 – kontroll av säkerhetskopieinode och immutable snapshot före restore
- URL: https://github.com/Harrokk/Myai/pull/132
- Branch: `dev/selfdev-backup-snapshot-20261014`
- Verifierat commit: `bbcd2a49850c52acfbd2c67c30005d5b4ca46e36`
- Full VENTUNO Q ARM64 suite: https://github.com/Harrokk/Myai/actions/runs/38543923408 – **1583 passed, 6 skipped**.
- En säkerhetskopia var tidigare hashkontrollerad på sökvägen och senare öppnad igen via shutil.copy2, vilket gav möjlighet att byta ut filen mellan kontrollerna.
- Ny `_backup_verified_snapshot()` öppnar källbackup med O_NOFOLLOW/O_NONBLOCK där tillgängligt, kontrollerar via fstat riktig ensam filinode, kopierar data från redan öppnad fd till en exklusiv privat temporär snapshot i rollbackkatalogen, verifierar SHA-256 mot autentiserad journal och fsync:ar innan `_atomic_copy` får använda snapshoten. Återställer ordinarie filrättigheter och städar snapshots även vid simulerat SystemExit i Python.
- Tre nya tester: backup symlink swap efter första preflight, ändring av backupinnehåll i kontrollfönstret och kontroll av ursprungligt filläge/inga temporära restfiler.
- Första testkörningen av denna gren hade två fel eftersom nya simuleringar träffade den tidigare backupkontrollen; korrigerades att injecta efter snapshotens kontroll, och ny full suite passerade.

## Konsekvent begränsad säkerhetsbedömning
- Projektlåset är **advisory** och kräver samarbete av MyAI-processer. Någon med samma UID och skrivbehörighet till alla filer/kataloger kan inte stoppas av enbart inodekontroller och SHA-256.
- Tillagda privata UNIX-rättigheter stoppar vissa felkonfigurationer och andra lokala användare, men utgör inte fullständig privilegieseparation för nyckeln. En separat tjänstanvändare eller OS-baserad skyddad hemlighetslagring skulle kräva egen design och explicit driftsättning.
- Restore snapshot ligger temporärt i privat rollbackkatalog. En oförutsedd OS-kill/power-loss kan lämna en föräldralös `.verified-backup-*.tmp`; dessa bör identifieras och städas genom en separat säker, ej automatiskt destruktiv process.
- Återställning är fortfarande skyddad med manuell godkännandefras och autentiserad journal, men verkliga power-loss- och flerprocess-race behöver vidare analys. Inga fysiska strömavbrottstest har gjorts, ingen automatisk promotion har aktiverats och ingen faktisk systemtjänst ändrats.
- Full VENTUNO Q ARM64 suite skippar sex frivilliga host-only ONNX/NumPy-fall. De verifierades tidigare i 22 godkända test på GitHub-hostad x86 Linux: https://github.com/Harrokk/Myai/actions/runs/38520039444.
- GitHub Support-historikcache-fallet med tidigare känsliga SQLite-uppgifter kvarstår enligt blocker-PR #110. Alla relevanta draft-PRs #112, #113, #114, #115, #116, #119, #120, #122, #123, #124, #125, #126, #127, #128, #129, #130, #131, #132 ska fortsatt granskas innan main merge.
- Windows Arduino App Lab invalid-IP-felsökning är pausad på begäran. Inga live mikrofon-, USB-ljud-, Bluetooth-, kamera-, GPS-, STM32- eller NPU-experiment genomfördes.

## Nästa möjliga autonoma steg
- Analysera hur temporära `.verified-backup-*` kan visas i skrivskyddad diagnostik utan att radera säkerhetskopior eller lita på symlänkar.
- Sök andra tillfällen där en hashkontrollerad fil öppnas igen utan no-follow fd, särskilt preflight till `os.replace` samt audit-loggens kataloger.
- Kontrollera om loggning före behörighetsgrind kan följa en skadlig `runtime`-symlink, och skissa säker fail-closed-lösning med tester som inte skadar andra revisionsloggar.
- Överväg tydlig policy för drift under gruppdelat installationsträd; behörighetskontroll vägrar numera gruppskrivbara runtime-kataloger och kräver separat migrationsbeslut.
