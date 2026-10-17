# MyAI – läs-only inventering av kvarlämnade rollback-snapshots (2026-10-17)

**Bas:** DRAFT PR #297, SHA `59283a9d0bbc975aac54138aa7bc1dca6cc1a3e4`, ARM64 3397 pass/15 skip. Ny DRAFT-gren `dev/manual-audit-selfdev-orphan-inventory-dirfd-20261017`. Inga aktiva filer, tjänster, mikrofoner, NPU, promotion- eller återställningsoperationer körs.

## Tvåpassig manuell granskning

**Pass 1 – logik/flöde:** `SelfDevPromotionManager.inspect_recovery_artifacts` inventerar överblivna `.verified-backup-*.tmp` efter avbruten rollback. Den tidigare rutinen använde `Path.is_symlink`, `Path.exists/is_dir`, en `stack` av `Path` och `os.scandir(directory)` via öppnande av samma pathname om och om igen. En samtidiga katalogaliasflytt efter länkkontroll kunde därmed omdirigera läsningen till annat innehåll. Eftersom metoden ska vara skrivskyddad och informativ kan det ge felaktig inventeringsrapport eller oavsiktlig läsning av externa katalognamn.

**Pass 2 – säkerhet/avgränsad fix:** `inspect_recovery_artifacts` anropar `_pinned_parent(backup_root)` och öppnar dess slutkatalog med `O_DIRECTORY|O_NOFOLLOW`. En saknad valfri backupträdrot ger fortfarande `no_artifacts`. Symlänkar i något katalogled blockerar med tydlig orsak. Varje katalog behålls som en öppen FD i arbetsstacken, `os.scandir(fd)` ger bara namn, och varje barn `os.stat(name,dir_fd=...,follow_symlinks=False)` granskas. Underkataloger öppnas no-follow relativt redan öppnad förälder; inode och dev jämförs mellan stat och fstat. Fel leder till `blocked`, aldrig till följande av extern symlänk. Temporära återställningsfiler måste vara vanliga filer med en hårdlänk. Ingen fil öppnas för dataläsning och inga kataloger eller filer raderas. Alla FD stängs även vid fel; 5 000 poster och 40 nivåer begränsar inventeringen.

### Säkerhetsregressioner

Tre nya syntetiska tester: (1) backup-roten flyttas och ett namn ersätts med extern symlänk efter att dess FD öppnats: inventeringen läser fortfarande bara den öppna rotens poster; (2) en underkatalog byts till en extern symlänk före öppning: inventeringen blockeras; (3) en mellanliggande rollback-förälderkatalog är symlänk från början: inventeringen blockeras utan extern traversering. Befintliga tester för symlänkar i backup, read-only-stabilitet, orphan-räkning och saknade promotion-ID finns kvar.

## Kvarstående release-blockerande risker

- En privilegierad icke-samarbetande writer kan fortfarande byta innehållet i **samma öppna kataloginode** under inventeringen eller skapa nya filer efter kontrollen. Detta är en lägesrapport, inte en oavvislig snapshot.
- Efterföljande aktiv recovery och rollback har andra katalog-/journal-/stagingsteg och kräver individuell verifiering. Filägande, UID-isolering och privat sessionroot måste vara säkra.
- Den kompletta manuella filgranskningen, DNS/SSRF, SBOM/licenser/nativa beroenden, verklig strömavbrottsåterställning samt fysiska VENTUNO NPU- och rösttester återstår.
- Ingen merge till `main`, ingen utrullning till `/home/arduino/MyAI`, ingen aktiv selfdev.

**Krav:** fullständig source-only ARM64-projektsvit på exakt sista commit.
