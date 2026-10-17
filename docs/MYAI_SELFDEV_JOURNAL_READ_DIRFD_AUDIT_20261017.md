# MyAI – återställningsjournal: säker läsning och enhetlig inode (2026-10-17)

**Bas:** PR #283 vid `4642569e16981bc370643e5ba00ae3f3a0b09ad4`. **Gren:** `dev/manual-audit-selfdev-journal-read-dirfd-20261017`. Bara DRAFT-kod och syntetiska offline-test på VENTUNO self-hosted runner; ingen aktiv installation, promotion eller rollback.

## Pass 1: flöde

`SelfDevPromotionManager._read_recovery_json` öppnade `os.open(str(path), O_NOFOLLOW)` och använde `fstat` för regular file och en-länkskontroll samt 1-MiB-gräns. Läsningen dekodade UTF-8, nekade dubbla JSON-nycklar och NaN/Infinity och användes därefter för HMAC-validering. Slutfilens symlänk kunde inte följas, men en förälderkatalog kunde bytas till symlänk precis före öppning; `O_NOFOLLOW` på slutledet skyddar inte mot detta.

## Pass 2: åtgärd

- `_read_recovery_json` använder `_pinned_parent(Path(path))` som öppnar alla katalogled med `O_DIRECTORY|O_NOFOLLOW` och håller directory-fd öppen tills slutfilen öppnats.
- Slutfilen öppnas via `os.open(name, O_NOFOLLOW|O_NONBLOCK, dir_fd=directory_fd)`, `fstat` kräver vanlig fil med en hårdlänk och storlek högst 1 MiB. Efter begränsad läsning jämförs inode, storlek, mtime och ctime för att upptäcka samtidig ändring.
- Existerande strikt JSON-avkodning (dubbla fält, ickeändliga tal, UTF-8, HMAC efter parsning) bibehålls. Länk- och permissionfel behandlas som blockerad läsning.
- Fyra offline-tester: bytt förälderkatalog före öppning, bytt filalias **efter** öppning, modifierad öppen inode under läsning och befintlig symlänk i förälderkatalogen. Existerande recovery, journal-, backup- och idempotenssvit körs samtidigt.

## Fortsatt NO-GO

- En lokal process med skrivrätt kan mutera en giltig journal efter denna enskilda läsning; journalens autentiserade HMAC skyddar innehållets integritet, men full filsystemisolering kräver separata användar-/katalogrättigheter.
- Full rollback-backup-`_verified_backup/_backup_verified_snapshot` använder fortfarande vissa path-baserade kontroller för parentkataloger, och första backup från aktiv kod via `shutil.copy2` återstår.
- Journalens HMAC-nyckel, käll-/målrenamemiljö, hardlinks, bind mounts, hantering av stor mängd filer och fysisk recovery vid strömavbrott behöver egen hotmodell/tester.
- Hela repositoryts manuella filrevision, full nativ SBOM och licenser, hårdvaru-NPU/ljud och releasebeslut har inte slutförts. Alla PR förblir **DRAFT**; inget main-merge och ingen installation.

Verifieringskrav: full ARM64 source-only CI på exakt sista commit, inga aktiva system- eller nätverkstester.
