# MyAI — rollback: descriptorförankrade temporära backup-snapshots (2026-10-17)

**Bas:** PR #286 commit `212d560245c3cb96d568f3144aa55be3083ecd73`. **Gren:** `dev/manual-audit-selfdev-backup-snapshot-dirfd-20261017`. Endast DRAFT-kod/source-only CI, inga aktiva eller fysiska ändringar på VENTUNO.

## Pass 1: logik

`SelfDevPromotionManager._backup_verified_snapshot()` läste redan verifierad backup via en no-follow filbeskrivare efter PR #286, men skapade själva `.verified-backup-*.tmp` via `tempfile.mkstemp(dir=str(backup.parent))`. Även `snapshot.unlink()` och `_sync_directory(snapshot.parent)` använde namn som kunde ompekas till annan katalog. En icke-samarbetande lokal process med möjlighet att byta backupens förälderkatalog kunde därför omdirigera just snapshot-skapning eller städning. Återställning använder därefter `_atomic_copy(snapshot,target)`, som redan skyddar eget slutmål, men denna tidiga filoperation återstod.

## Pass 2: säkerhet och åtgärd

- `_backup_verified_snapshot()` håller `_pinned_parent(backup)` öppen över **hela contextmanager-tiden inklusive `yield`**, så att ett ompekat katalogalias inte kan styra efterföljande skapan-/raderingsanrop.
- Backup öppnas `O_RDONLY|O_NOFOLLOW|O_NONBLOCK` via samma katalogbeskrivare och `fstat` kräver vanlig fil med en hårdlänk.
- Temporär snapshot skapas exklusivt med slumpat `.verified-backup-<nonce>.tmp` via `os.open(... O_CREAT|O_EXCL|O_NOFOLLOW,dir_fd=parent_fd)`, mode 0600. Bytes kopieras i block och SHA-256 jämförs mot förväntad journalhash **innan snapshot släpps till konsumtion**. Storlek, inode, mtime och ctime jämförs före/efter för att upptäcka ändringar under kopiering.
- Fil-fsync och katalog-fsync görs före `yield`. Temporär snapshot tas alltid bort i `finally` med `os.unlink(name,dir_fd=parent_fd)` och katalogen synkas. Vid exception under kopiering eller i caller städas endast denna tillåtna katalog.
- Befintligt snapshot-Path API bevaras för att inte ändra projektets promotion/rollback-callers. Tre nya syntetiska tester täcker ompekat backupkatalogalias efter att snapshot-fd skapats, städning efter en caller-exception samt redan upptaget temporärt namn som symlänk.
- De befintliga fullständiga promotion-, återställnings- och journaltester ska fortsatt vara gröna.

## Kvarstående NO-GO

- `snapshot` exponeras fortfarande som en **pathname** till `_atomic_copy`, som återöppnar filen. Den operationen har O_NOFOLLOW på varje katalogled men ett bortflyttat originalalias kan göra återställning omöjlig (fail-closed). Nästa hårdare alternativ är att föra snapshot-fd vidare i stället för pathname.
- Inga OS-filsystem-API:er i denna patch kan ge atomisk compare-and-swap mot en privilegierad icke-samarbetande writer, hårdlänks-/mount-manipulation eller full proveniens mot komprometterad UID.
- `_safe_backup_path`, `_journal_integrity_key`, vissa sökvägskontroller, förälderkatalogägarskap, och städning av hela misslyckade promotionmappar behöver fortsatt systematisk audit. Journalens HMAC och projekträttigheter är separata skyddsbarriärer.
- Fullständig manuell 850+-filers kod- och beroenderevision, SBOM/licens/ABI, fysisk NPU/röst och verifierad strömavbrottsåterställning återstår.
- Ingen merge, deployment eller aktiv selfdev-exekvering är auktoriserad. Exakt slut-SHA kräver grön full ARM64 source-only CI.

**Status:** DRAFT, ej releasegodkänd.
