# MyAI – fsync efter atomär kodersättning: endast öppnad katalog-FD (2026-10-17)

**Bas:** DRAFT PR #295, exakt SHA `817351d92615f44c43cd337694d482cde7266a7b`. **Gren:** `dev/manual-audit-selfdev-postrename-fsync-dirfd-20261017`. Endast källkod och syntetiska ARM64-tester; inga aktiva promotions/rollbacks eller ändringar i VENTUNO-installationen.

## Granskningspass 1 – upptäckt race

`_atomic_copy(source,destination)` öppnar redan källan och målkatalogens alla föräldrar med `_pinned_parent`, verifierar bytes och källans stabilitet, skapar en exklusiv temporär fil, och gör `os.replace(temporary,target_name, src_dir_fd=...,dst_dir_fd=...)` på den öppnade målkatalogen. Därefter utförde koden både `os.fsync(target_parent_fd)` och en extra `_sync_directory(destination.parent)`. Den senare öppnade **sökvägen igen efter att destinationen bytts** och kunde peka på en annan katalog om någon ändrade dess förälderalias. Den andra synkroniseringen behövdes inte för hållbarhet eftersom samma målkatalogs FD redan hade synkats.

## Granskningspass 2 – avgränsad fix och testning

- Den extra `_sync_directory(destination.parent)` tas bort helt. Den tidigare `os.fsync(target_parent_fd)` efter `os.replace` behålls, liksom temporär fils `fsync` före ersättningen, kontroll av innehåll och no-follow-katalogankring.
- Det befintliga `test_directory_fsync_failure_after_rename_restores_original` injicerar nu ett syntetiskt `OSError` på den **faktiska öppnade katalogens `os.fsync(fd)`** genom att identifiera dess `st_dev/st_ino`. Testet verifierar att aktiv kod återställs och journalen markeras som `reverted` om just den hållbarhetskritiska synkroniseringen misslyckas.
- Ett nytt regressionstest byter målkatalogens sökväg till en extern symlänk direkt **efter** descriptor-relativ `os.replace` men före efterföljande `fsync`: originalkatalogens redan öppnade inode är synkroniseringsmål, verifierad kod hamnar enbart där, och extern skyddad fil är oförändrad. Path-baserad synkronisering förbjuds uttryckligen i testet.
- Samtliga tidigare promotion/backup/rollback/journal-regressioner och full ARM64 source-only-svit används.

## Öppna risker och release NO-GO

- En osamarbetsvillig skribent med skrivrätt kan byta ett filnamn mellan kontrollen av förväntad tidigare fil och `os.replace`. POSIX ger ingen inbyggd atomisk compare-and-replace för godtyckliga inoder; UID- och katalogisolering är fortfarande nödvändigt.
- Att en katalog-FD synkas är inte ett fysiskt test av eMMC:s beteende vid strömavbrott. Beroenden, nativ ABI, SBOM/licenser, hela projektets fil-för-fil-säkerhetsgranskning och VENTUNO:s ljud/NPU kräver separat verifiering.
- Denna PR tillåter inte merge till `main`, deployment, aktivering av selfdev, auto-rollback eller live promotion. All kod förblir DRAFT tills fullständig releasekontroll.

**Verifieringskrav:** fullständig ARM64 source-only-testsvit på exakt commit.
