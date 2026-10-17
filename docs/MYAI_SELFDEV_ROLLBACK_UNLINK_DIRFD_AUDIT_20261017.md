# MyAI – rollback: säker borttagning av nytillkomna filer (2026-10-17)

**Bas:** PR #281 commit `ab3e4895942b469366101687cb124054bec3341a`. **Gren:** `dev/manual-audit-selfdev-rollback-unlink-dirfd-20261017`. Source-only DRAFT, ingen aktiv promotion/rollback på installerad VENTUNO.

## Manuell granskning – pass 1 (funktion och kontrollflöde)

`SelfDevPromotionManager._restore_from_backup()` används av felhantering i `_promote_impl()`, av `_recover_interrupted_impl()` och av `_rollback_impl()`. Om en promotion hade introducerat en helt ny kodfil (`backups[relative]["existed"] == False`) gjorde funktionen tidigare `target.unlink()` genom absolut sökväg. Underkatalogerna kontrollerades via `_safe_project_target()`, men därefter sker en separat sökvägsuppslagning vid unlink. Funktionen tog ingen hashparameter för den nya filen och verifierade därför inte att dess aktuella innehåll fortfarande motsvarade vad den ursprungligen promoverade kodversionen innehöll.

## Manuell granskning – pass 2 (säkerhet och begränsad åtgärd)

- Ny `_unlink_verified_added(target,expected_hash)` kräver en giltig 64-teckens SHA-256-hexsträng från journalens verifierade `planned_hashes` eller `after_hashes`. Okänd hash innebär **ingen borttagning**.
- Filens föräldrakatalog förankras i descriptor med `_pinned_parent` och `O_DIRECTORY|O_NOFOLLOW`. Slutfilen öppnas via `dir_fd` med `O_NOFOLLOW|O_NONBLOCK`, `fstat` kräver vanlig fil med exakt en hårdlänk.
- Hashning utförs mot redan öppnad filbeskrivare. Efter hashningen kontrolleras filnamnets aktuella `st_dev, st_ino, st_size, st_mtime_ns, st_ctime_ns, st_nlink` utan symlänksföljning. Filen raderas bara om kontrollerna matchar och samma öppnade förälderkatalog används med `os.unlink(name, dir_fd=...)`, följt av katalog-fsync.
- Alla tre anrop till `_restore_from_backup()` skickar nu förväntade efter-hashar. Återställning av redan befintliga filer använder tills vidare tidigare kontrollerade `_backup_verified_snapshot` och `_atomic_copy`.
- Fem nya regressionstester: slutfilssymlänk avvisas, externt ändrad fil bevaras, sent ompekat föräldraalias kan inte radera extern fil, sent ompekad slutfil avvisas vid stat, saknad hash avvisas.

## Kända kvarvarande risker / release NO-GO

- POSIX `unlink()` erbjuder inte en atomär jämför-inode-och-radera-operation. En samtidigt skrivande process kan i teorin byta själva filnamnet mellan sista `stat` och `unlink`. Projektets advisory lock skyddar bara samarbetsvilliga processer; skydd kräver UID-/katalogbehörigheter eller att koden körs mot exklusivt kontrollerad staging. Detta är fortfarande en **öppen** hotmodell.
- Backup- och återställningskällor använder ännu `_verified_backup()`/`_backup_verified_snapshot()` med separata path-baserade kontroller; första backup-skapandet använder `shutil.copy2` och kan behöva förbättrad filidentitet och atomäritet. Journalen `_atomic_write_record` gör också pathname-rename och ska härdas separat.
- Bakåtkompatibel `_safe_project_target` och övriga befintliga testmetoder ändrades inte för denna patch. Fysisk power-loss/crash-konsistens, källproveniens, nativa beroenden, SBOM, licenser, ljud/NPU och fullständig manuell fil-för-fil-revision kvarstår.
- Ingen merge till main, ingen installation och inga riktiga rollback-/promotion-exekveringar. Testa isolerat på exakt sista commit i GitHub Actions ARM64.

**Status:** Kodfix incheckad, regressionsbevis måste verifieras på exakt HEAD. Detta är inte en komplett säkerhetsattest.
