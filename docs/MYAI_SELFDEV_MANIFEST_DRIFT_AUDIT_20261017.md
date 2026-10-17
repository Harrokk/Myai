# MyAI – manuell revision av selfdev-manifest och source_drift (2026-10-17)

**Granskad bas:** DRAFT PR #277 vid `d64ed6f9818368a6e09615c293795a4acfa370c3`. **Ny gren:** `dev/manual-audit-selfdev-manifest-drift-20261017`. Ingen merge till main, ingen installation eller körning av aktiv selfdev-promotion på VENTUNO.

## Pass 1: befintliga kontrollflöden

- `build_manifest(root)` använde `root.rglob("*")`, följt av `path.is_file()` och `path.is_symlink()`, därefter `_sha256(path)` som **öppnade pathname på nytt**. Listningen kunde betrakta en fil som säker men hashningen följa en sent utbytt symlänk.
- `source_drift()` itererade `metadata()['baseline']` och beräknade `self.project_root / relative` direkt från JSON-innehåll, sedan `source.exists()` och path-baserad `_sha256(source)`. Förfalskade baseline-nycklar med `../` kunde därmed öppna filer utanför projektträdet. Detta är **en separat obetrodd-metadata-lucka** utöver TOCTOU-racet.
- `SelfDevVerifier.verify()`, `SelfDevPromotionManager` och granskningsflödet anropar manifest/drift. Felaktig filidentitet kan försvaga deras underlag, men deras egna behörighets- och approvalsgränser är separata.

## Pass 2: genomförd åtgärd

- Delad `_hash_pinned_regular_file(fd)` kräver vanlig fil via `fstat()`, hashar i begränsade block från **redan öppen** fil-descriptor och avvisar upptäckbar storleks-, inode-, mtime- och ctime-drift.
- `build_manifest()` listar enbart allowlistade kataloger/filer från descriptor-förankrad rot. `os.scandir(fd)`, `os.stat(..., dir_fd=fd, follow_symlinks=False)` och `os.open(..., O_NOFOLLOW, dir_fd=fd)` tar bort path-check/open-racet för vanliga filer och underkataloger. Sent utbytta länkar avvisas.
- `source_drift()` kontrollerar att metadata är ett dictionary med strikt tillåtna relativa filvägar och SHA-256-hexsträngar. `_hash_allowed_relative()` öppnar varje path-komponent utan symlänksföljning. Borttagna, oåtkomliga och till symboliska länkar ändrade filer räknas som drift. Förfalskade `../`-nycklar avvisas **före I/O**.
- Plattformar utan Linux/POSIX `O_DIRECTORY` och `O_NOFOLLOW` får ett explicit fel, inte en osäker fallback.

## Sju syntetiska regressionstester

1. Manifestet motsvarar staging-baseline byte för byte och ignorerar befintlig extern filsymlänk.
2. Fil blir en symlänk direkt före manifest-öppningen; extern fil öppnas inte.
3. Katalog blir en symlänk direkt före dirfd-öppningen; extern katalog öppnas inte.
4. Source-drift detekterar om ursprungsfilen ersätts med symlänk.
5. Source-drift detekterar om en tillåten förälderkatalog ersätts med symlänk.
6. Manipulerad `../`-nyckel i sessionsbaseline avvisas före hashning.
7. Fil ändras under manifest-hashning och nekas.

## Öppet och releaseblockerande

- JSON-metadata läses fortfarande från pathname `session.json` utan dirfd/no-follow, och `verification.json` skapas/läses/raderas från andra självdev-komponenter; de kontrollerna har **inte** härdats här. Detta blir nästa separat granskade patch.
- `core/selfdev_promote.py` har flera egna pathname-baserade käll-/mål-/journaloperationer. Denna manifeständring **härdar inte promotion eller rollback** automatiskt.
- Det finns fortsatt risk för hardlinks, bind mounts, omflyttning av redan öppna inoder, ändringar som sker före/efter mätt tidsfönster, mycket stora kataloger/djup rekursion, OS-kontroll och falsk sessionsmetadata med formellt korrekta hashvärden. Full filproveniens behöver immutable snapshot och/eller betrodd signering.
- Komplett manuell filgranskning av hela repositoryt, SBOM/native dependencies/licenser och fysiska ljud-/NPU-test samt oberoende releaseprövning återstår. **DRAFT/NO-GO.**

**Verifieringskrav:** syntetiska tester och full ARM64 source-only suite på exakt sista commit. Ingen CI-körning ersätter fysisk eller säkerhetsmässig slutattest.
