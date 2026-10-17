# MyAI – skapande och hållbar publicering av rollback-kataloger (2026-10-17)

**Bas:** verifierad DRAFT PR #293, exakt SHA `a99804c82dcea714db61276abe8f5e28ab173fdd`. **Gren:** `dev/manual-audit-selfdev-rollback-root-dirfd-20261017`. Ändringar endast i GitHub-källkod, ingen aktiv selfdev-operation eller utrullning till VENTUNO.

## Pass 1 – logik och kontrollflöde

`SelfDevPromotionManager._promote_impl()` skapade tidigare `session_root/rollbacks/<promotion_id>` genom `rollback_root.exists()`, sedan `rollback_root.mkdir(parents=True,exist_ok=False,mode=0o700)` och därefter separat `_sync_directory(rollback_root.parent)` respektive `_sync_directory(rollback_root.parent.parent)`. En process med möjlighet att byta ut `rollbacks`-föräldern kunde omdirigera katalogskapningen eller efterföljande synkronisering mellan dessa path-baserade steg. En slutlig symlänk kunde också konkurrera med preflight-kontrollen.

## Pass 2 – begränsad härdning

- `_create_private_rollback_root(rollback_root)` ersätter denna sekvens. Den befintliga sessionens föräldrar öppnas med `_pinned_parent(rollback_root.parent)`, som kräver absolut sökväg och `O_DIRECTORY|O_NOFOLLOW` på varje katalogled; den skapar inga alternativa sessionsträd.
- Den öppnade sessionskatalogen kontrolleras via `fstat` för katalogtyp, egen UID och avsaknad av grupp-/världsskrivning.
- Den valfria `rollbacks`-föräldern skapas endast genom `os.mkdir(name,mode=0700,dir_fd=session_fd)`. Samma katalog öppnas via `os.open(name,O_DIRECTORY|O_NOFOLLOW,dir_fd=session_fd)` och kontrolleras för UID och skrivbehörigheter.
- Den privata promotion-ID-katalogen skapas exklusivt via `os.mkdir(promotion_id,mode=0700,dir_fd=rollbacks_fd)`, så en redan befintlig katalog eller symlänk ger `FileExistsError` i stället för att återanvändas. Öppnad katalog-FD och slutnamn jämförs genom `fstat` och `stat(...follow_symlinks=False)`. Själva privatkatalogen kräver ingen grupp-/världsåtkomst alls.
- Först när alla kontroller lyckats görs `fsync` på privatkatalogen, dess `rollbacks`-förälder och sessionskatalogen med redan öppnade FDs, innan första backupfilen skrivs.
- Fem nya offline-tester: vanlig privat och exklusiv skapning, ompekat föräldernamn till symlänk före öppning, ompekat föräldernamn **efter** öppning, befintlig slut-symlänk och grupp-/världsskrivbar förälder.
- Samtliga tidigare tester för backup, HMAC, journal, rollback och avbrott ingår i den fulla ARM64-projektsviten.

## Kvarvarande risker – fortsatt NO-GO

- OS erbjuder inte atomisk jämförelse av öppnad inode och senare namnanvändning under godtycklig privilegierad lokal manipulation. Lokalt skrivbehöriga icke-samarbetande processer, bind mounts och hårdlänksgränser kräver starkare användar-/ägarmodell. Den globala flocken gäller endast samarbetsvilliga aktörer.
- Nästlad backup-katalogsynkronisering använder fortfarande `rglob` och `_sync_directory(path)`; denna PR säkrar enbart **startkatalogens skapning och första fsync**. Andra pathname-baserade filsystem- och återställningsvägar samt faktisk strömavbrottskonsistens ska granskas separat.
- Fullständig manuell kod- och beroenderevision/SBOM, licens-/native/ABI-verifiering, ljud/NPU och fysiska release-tester återstår. Ingen merge till `main`, ingen installation eller aktiv promotion/rollback.

**Verifiering:** hela ARM64 source-only GitHub Actions på exakt sista HEAD, utan aktiva tjänste- eller hårdvaruförändringar. DRAFT/NO-GO tills dess.
