# MyAI – selfdev rollback: säkrare läsning av verifierade backupfiler (2026-10-17)

**Bas:** DRAFT PR #285 på commit `9cc4ae4783230ae7aa9c6b6605746d644d1e566f`. **Gren:** `dev/manual-audit-selfdev-backup-read-dirfd-20261017`. Endast source-only GitHub-test; ingen verklig promotion, recovery eller rollback på VENTUNO.

## Granskningspass 1 – kodflöde

`SelfDevPromotionManager._verified_backup` gjorde `_safe_backup_path()` och `backup.lstat()`, därefter `_sha256(backup)`. Även om slutfilen avvisades som symlänk efter `lstat`, öppnades pathname på nytt för hashning. En förälderkatalog kunde bytas till en extern symlänk mellan dessa steg. `_backup_verified_snapshot` gjorde en ytterligare `os.open(str(backup), O_NOFOLLOW)` som skyddade sista komponenten men inte katalogerna ovanför. En attackerbar förälderkatalog kunde därför påverka backupens bytes eller vilken fil som användes i återställningen.

## Granskningspass 2 – avgränsad fix

- `_verified_backup` använder nu `_hash_existing_regular_path(backup)` från PR #285. Funktionen öppnar varje förälderkatalog med `O_DIRECTORY|O_NOFOLLOW`, öppnar slutfilen via den öppna `dir_fd` med `O_NOFOLLOW|O_NONBLOCK`, kontrollerar vanlig fil med exakt en hårdlänk via `fstat` och beräknar SHA-256 direkt från den låsta filbeskrivaren. Hashfel eller upptäckbara ändringar avvisas.
- `_backup_verified_snapshot` öppnar nu återigen varje förälderkatalog via `_pinned_parent`, samt slutfilen med ett relativt `os.open(name, ..., dir_fd=...)`; symlänksbyte under kontroll/öppning kan inte omdirigera till extern fil. Existerande avvisning av fel hash i själva snapshotkopieringen kvarstår.
- Tre nya offline-test: symlänkbyte av backupens förälderkatalog före verifiering, slutfil byts till symlänk mellan verifiering och snapshotöppning, samt ändrade backupbytes avvisas.
- Existerande rollback/recovery-/journal- och permissionsregressioner används för kontraktskontroll. `_verified_backup` behåller sitt `Path`-returvärde för befintliga callers och testinjektion.

## Öppna risker – NO-GO

- Den temporära `.verified-backup-*.tmp` skapas och städas fortfarande via `tempfile.mkstemp(dir=backup.parent)` och pathname. En lokalt skrivbehörig process kan byta katalogalias mellan verifierad öppning och temporär snapshot-skapning eller före återställande läsning. **Detta är ännu inte en komplett säker backup-restore-kedja.** En kommande fix bör flytta även snapshot-generering till dirfd eller föra vidare redan öppet snapshot-fd.
- `_atomic_copy` har en oatomär preflight mot icke-samarbetande writers, och andra backup-/rollback-/journal- och städvägar kan behöva separat OS- och UID-isolering.
- Varken fysiska strömavbrott, originalkällkodens provenance, fullständig fil-för-fil-granskning, nativ SBOM/licenser eller VENTUNO:s ljud/NPU är verifierade av denna patch.
- Alla ändringar förblir DRAFT/NO-GO för main och produktion. Inga installerade filer på VENTUNO ska ändras.

**Krav:** full ARM64 source-only projekt-/säkerhetssvit på exakt PR-slut-SHA.
