# MyAI – synkronisering av nästlade rollback-backupkataloger (2026-10-17)

**Bas:** DRAFT PR #294, exakt SHA `5cc233c7e1f90133e52f2740bff145b481b14e05`. **Gren:** `dev/manual-audit-selfdev-backup-fsync-dirfd-20261017`. Bara källkod och isolerad source-only ARM64-testning. Ingen aktiv promotion, rollback eller modifiering av installerade filer.

## Granskningspass 1 – hittad kvarvarande sårbarhet

Efter backup-kopieringen synkroniserade `_promote_impl` tidigare undermappar med `(rollback_root/"files").rglob("*")`, filtrerade med `parent.is_dir()` och öppnade sedan varje resultat igen via `_sync_directory(current_dir)`, följt av en ny pathname-öppning av `rollback_root`. En mellanliggande katalogs namn kunde bytas till symlänk mellan genomgång, typkontroll och fsync. Då kunde synkroniseringen gå mot annan katalog än backupen som nyss skrevs. Dessutom garanterade `rglob`-samlingen inte uttryckligen fsync på backupträdet `files/` självt.

## Granskningspass 2 – kodändring

- En ny `_sync_prepared_backup_tree(rollback_root)` öppnar rollback-rotens alla föräldrar via `_pinned_parent` med `O_DIRECTORY|O_NOFOLLOW`. Den öppnade rotkatalogens UID och 0700-liknande privata behörigheter verifieras via `fstat`.
- Finns `files` öppnas den med `O_DIRECTORY|O_NOFOLLOW` relativt rotens katalog-fd. Saknas den (t.ex. promotion med bara tillagda filer) synkas endast den öppnade rollback-roten.
- Djupet genomgås via `os.scandir(directory_fd)`. Varje barn kontrolleras med `os.stat(...follow_symlinks=False,dir_fd=...)`; undermappar öppnas via samma förälder och kontrolleras mot förväntat `st_dev/st_ino` och lokal UID. Deras namn kontrolleras igen efter den underliggande katalogens fsync. Symlänkar, specialfiler eller filer med multipla hårdlänkar avvisas innan PREPARED-journalen skrivs.
- Varje öppnad underkatalog synkas efter sina barn, inklusive `files/` och sist rollback-roten. Högst 10 000 poster och 40 nivåer behandlas; avvikelse medför avbrott före ändring av aktiv källkod.
- Fem nya syntetiska tester: normal nästlad fd-baserad fsync, fallet utan `files/`, symlänksfil i backupträdet, utbytt rollback-förälder före öppning och utbytt nästlad katalog före öppning.

## Kända gränser och återstående NO-GO

- Filträdets namn-/inodkontroller är inte atomiska gentemot en privilegierad icke-samarbetande process; kontroll mellan `stat` och `os.open` kan fortfarande kräva fail-closed, vilket koden gör i kontrollerade fall. En åtkomlig symlänk eller specialfil hindrar promotion.
- Filsystemet och enhetens strömavbrotts-/fsync-semantik måste fortfarande verifieras på fysisk VENTUNO. Käll-/backupfiler synkas separat innan denna steg, men en fullständig transaktionsgaranti är inte styrkt.
- Övriga åtgärder omfattar resterande `_sync_directory`-anrop efter aktiv kod-rename, journalens HMAC/UID-gränser, isolering mot lokal skribent, kataloginventering och fullständig projekt-/beroende-/licensrevision. Fysisk ljud/NPU-verifiering återstår.
- Alla PR förblir DRAFT; ingen merge till `main`, ingen installation och inga aktiva självmodifieringsoperationer.

**Verifiering:** obligatorisk fullständig ARM64 source-only CI på exakt PR-HEAD. 
