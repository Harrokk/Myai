# MyAI – journalens HMAC-nyckel och säker katalogankring (2026-10-17)

**Bas:** DRAFT PR #287, exakt SHA `aa7a99e2280c6b6d9833d8218c491b8d3e9fe310`. **Gren:** `dev/manual-audit-selfdev-journal-key-dirfd-20261017`. Endast källkodsändringar i GitHub och syntetisk source-only ARM64-testning.

## Granskningspass 1 – flöde och risk

`SelfDevPromotionManager._journal_integrity_key()` skyddar signerade promotion-/rollback-journaler med en 32-byte lokal nyckel. Befintligt flöde använde `_private_selfdev_directory` för en separat path-baserad ägar-/symlänkskontroll, men sedan `tempfile.mkstemp(dir=directory)`, `os.link(temporary,key_path)`, `os.unlink(temporary)` och slutligen `os.open(str(key_path),O_NOFOLLOW)`. Skyddet för slutfilen räcker inte om en förälderkatalog byts till symlänk mellan kontroll och skapande/publicering/läsning. Vid skapande uppstod ett potentiellt felaktigt nyckellager, medan en förfalskad läsning kunde störa integritetskontroller eller orsaka otillåten filåtkomst.

Befintliga viktiga kontrakt: befintlig HMAC-nyckel får aldrig återskapas/ersättas automatiskt; filen ska vara 32 bytes, vanlig fil, en länk, privata permissions, och publicering med en färdig fsync:ad tempfil. Alla misslyckanden ska stoppa promotion före skrivning av aktiv kod.

## Granskningspass 2 – ändring

- Behåller tidigare `_private_selfdev_directory(create=...)` som kompatibel driftkontroll, men förankrar **alla säkerhetskritiska filoperationer** via `_pinned_parent(key_path)`, som öppnar varje katalogkomponent med `O_DIRECTORY|O_NOFOLLOW`.
- Samma öppna privata selfdev-dirfd kontrolleras med `fstat` för katalogtyp, aktuell användares ägarskap och avsaknad av grupp-/världsskrivning.
- Skapar en exklusiv tillfällig nyckelfil `O_CREAT|O_EXCL|O_NOFOLLOW`, mode 0600, skriver 32 slumpbytes och `fsync`:ar. Publicerar med `os.link(temporary,filename,src_dir_fd=directory_fd,dst_dir_fd=directory_fd,follow_symlinks=False)` utan att skriva över befintlig nyckel. Tempfilen raderas och katalogen fsync:as via samma dirfd. En redan befintlig nyckel används bara om **hela** valideringen passerar.
- Läser publicerad nyckel med `O_RDONLY|O_NOFOLLOW|O_NONBLOCK` relativt samma dirfd. `fstat` verifierar vanlig fil, exakt en länk, 0600-liknande privata rättigheter, rätt UID och exakt 32 bytes; observerade inode-/metadataändringar under läsningen avvisas.
- Fem nya regressionstester: katalogbyte före öppning, katalogbyte vid hardlink-publicering, symlänkbyte före nyckelläsning, hårdlänkad befintlig nyckel och ändrade permissions.
- Nyckelns existens eller storlek och behörigheter repareras aldrig automatiskt. Ingen migration av gamla nycklar sker.

## Fortsatta release-blockerande risker

- `_project_mutation_lock` öppnar ännu sin fil via pathnamn efter separat pathkontroll; detta bör härdas som nästa avgränsade moment.
- `_private_selfdev_directory(create=True)` gör pathname-baserad katalogskapning. Nyckeloperationerna är dirfd-förankrade, men andra komponenter behöver fortsatt genomgång av kataloghierarkin och ägargränsen.
- En privilegierad eller icke-samarbetande lokal process med skrivrätt kan manipulera redan öppna inoder, UID-/mount-gränser och filsystemet, vilket denna fix inte löser. En HMAC-nyckel är inte en signatur från oberoende release-aktör.
- Rollback/backup/snapshot-konsistens vid strömavbrott, nativa beroenden/SBOM, komplett fil-för-fil-revision samt fysisk VENTUNO-röst/NPU är fortfarande NO-GO.
- Ingen merge till main, ingen aktiv selfdev-promotion/rollback, ingen utrullning. Kräver fullständig ARM64 source-only CI på exakt sista commit.

