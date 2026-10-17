# MyAI – misslyckad pre-journal backup: säker städning (2026-10-17)

**Bas:** DRAFT PR #292, exakt SHA `d02254e23888826a48b9600c496005215024cbbb`. Ny DRAFT-gren: `dev/manual-audit-selfdev-rollback-cleanup-dirfd-20261017`. Endast GitHub-källkod och source-only ARM64-tester, ingen aktiv självmodifiering eller återställning.

## Pass 1 – manuellt genomgånget kodflöde

`SelfDevPromotionManager._promote_impl()` skapar en rollback-katalog, kopierar och synkar backupfiler och skriver först därefter en PREPARED-journal. Om något i backupfasen misslyckas görs ingen aktiv kodförändring, och den gamla felstädningen använde `shutil.rmtree(rollback_root)`. Trots skydd mot symlänkar i själva backupkopieringen kunde en mellanliggande förälderkatalog bytas efter kontroll men före `rmtree()`, så städningen kunde styras till ett externt katalogträd. `rmtree` har plattformsberoende skydd för vissa symlänksbyten men kan inte på egen hand garantera att **alla föräldraled** fortfarande är de förväntade.

## Pass 2 – isolerad säkerhetsfix

- `_discard_unprepared_backup_tree(rollback_root)` ersätter path-baserad `shutil.rmtree()` **enbart före att journalen publicerats**. Den öppnar föräldrakataloger med `_pinned_parent()` (`O_DIRECTORY|O_NOFOLLOW`) och backupens privata rot med `O_NOFOLLOW`. Rötternas inode, UID och privata permissions kontrolleras.
- Rekursiv innehållsgenomgång använder `os.scandir(directory_fd)`, `os.stat(name, dir_fd=..., follow_symlinks=False)`, och öppnar underkataloger med `O_DIRECTORY|O_NOFOLLOW`. Regular files kräver en enda hårdlänk och matchande inode/UID innan `os.unlink(name, dir_fd=...)`; kataloger kontrolleras före `os.rmdir(name, dir_fd=...)`.
- Alla raderingar sker relativt **redan öppna** föräldrar och varje katalog-fd fsync:as efter städning. Därmed kan ett sent byte av ett yttre katalogalias inte dirigera raderingen till ett annat träd.
- Om backupträdet innehåller symlänkar, specialfiler, oväntade hårdlänkar eller bytt inode ska operationen **avbrytas** hellre än radera osäkert innehåll. Max 10 000 inspekterade poster och 40 nivåers djup.
- Fem offline-regressionstester: normal nästlad radering; sent utbytt backupförälderalias; symlänk i förälder före öppning; osäker symlänk inne i backupträdet; filnamn byts till symlänk före slutfilens öppning. Befintligt tester för syntetiskt backupfel och rollback/recovery testas tillsammans.

## Fortsatta begränsningar / release NO-GO

- Detta är **inte** en atomisk jämför-inode-och-radera-operation på Linux. En privilegierad icke-samarbetande skribent kan fortfarande byta ett tillåtet slutnamn mellan sista `stat` och `unlink/rmdir`. Säkert driftläge kräver privat process-UID och skrivskyddade projekt-/sessionföräldrar.
- Katalogskapningen `rollback_root.mkdir(parents=True,...)`, katalog-fsync från pathname, nästlad backup-`rglob`, `_safe_backup_path.resolve`, recover-inventering och flera läskontroller behöver fortsatt säkerhetsgranskning. I denna PR har enbart det gamla farliga **pre-journal-städflödet** bytts ut.
- Vid upptäckt manipulation lämnas eventuella ofullständiga säkerhetskopior kvar för **manuell** sanering. Det är avsiktligt; aktiv kod har ännu inte modifierats när denna cleanup används.
- Full repositoryrevision, beroenden, firmware/ABI, licenser/SBOM, VENTUNO NPU/ljud samt fysisk recovery vid strömavbrott återstår. Samtliga PR:er förblir DRAFT, ingen merge/deployment.

**Krav:** full ARM64 source-only GitHub Actions på exakt sista commit, utan aktiva tjänsteändringar.
