# MyAI – säkrare backupmålsökvägar i selfdev (2026-10-17)

**Bas:** PR #291, SHA `7c73fb4cb269851322057f59fef7feaff7e3ed5c`. **Gren:** `dev/manual-audit-selfdev-backup-path-dirfd-20261017`. Källkod i DRAFT och offline ARM64-körning; ingen live promotion eller rollback.

## Pass 1: flöde och risk

`SelfDevPromotionManager._safe_backup_path()` producerar en tillåten kodbackup-path utifrån signerad journalmetadata eller planerad promotion. Den gamla funktionen gjorde `root.is_symlink()`, `base.is_symlink()`, `is_symlink()` på successiva path-komponenter samt separata `base.resolve(strict=False)` och `current.resolve(strict=False)`. Även om den kontrollerade att backup låg under `files/` kunde en lokal writer ompeka en förälderkatalog under kontrollerna. `resolve()` kunde också följa en tillfälligt utbytt symlänk innan efterföljande backup I/O. Senare skapande och verifikation använder sedan tidigare skyddade filbeskrivare, men tillåtelsekontrollen behövde bli konsekvent.

## Pass 2: åtgärd och regression

- Behåller `_allowed_relative_path` och oförändrat `Path`-returvärde för kompatibilitet med skapande, backupverifiering och återställning.
- Förankrar `rollback_root` med `_pinned_parent(root / ".selfdev-backup-root-check")` som öppnar varje förälderkatalog med `O_DIRECTORY|O_NOFOLLOW`.
- Öppnar sedan befintliga `files/` och mellanliggande backupkataloger med `os.open(component, O_DIRECTORY|O_NOFOLLOW, dir_fd=...)`, utan `Path.resolve()`.
- En ännu saknad `files/`-katalog eller tillåten underkatalog accepteras under det första backup-skapandet. Om slutnamnet redan finns krävs vanlig fil; symlänk och specialfil nekas med `PermissionError`.
- Fem syntetiska regressionstester: saknad `files/` accepteras, redan existerande föräldersymlänk nekas, förälderkatalog ompekas precis före öppning, slutfilssymlänk nekas och symlänkad `rollback_root` nekas.

## Kvarvarande NO-GO

- Detta säkrar path-**preflight**, inte en atomär koppling mellan kontroller och senare mutation. Befintliga `_copy_verified_backup`, `_verified_backup` och `_backup_verified_snapshot` använder egna no-follow-filbeskrivare, men privilegierad kod kan byta katalogalias eller mount.
- `_require_no_interrupted_promotion`, recovery-artefaktinventering, cleanup `shutil.rmtree(rollback_root)`, legacyjournal-migrering och staging-sessionens egen katalogskapning har fortfarande path-baserade kontroller som kräver separata revisioner.
- Globala låset är endast rådgivande mellan samarbetsvilliga processer. Explicit UID-isolering, native SBOM/licenser och fysisk VENTUNO-kontroll är egna releasekrav.
- Fullständig manuell fil-för-fil-granskning och faktisk rollback/power-loss-testning är ännu inte avslutade. **Ingen merge, deployment eller aktivering**.

**Krav för teknisk verifiering:** grön full ARM64 source-only-testsvit på exakt sista commit.
