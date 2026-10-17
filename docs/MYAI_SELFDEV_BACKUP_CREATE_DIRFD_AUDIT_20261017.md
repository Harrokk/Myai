# MyAI – selfdev promotion: backup-skapande från en enda låst inode (2026-10-17)

**Bas:** grön DRAFT PR #284, SHA `69bcde937f13acfeb0aaf7ddd52d728db586defb`. **Ny gren:** `dev/manual-audit-selfdev-backup-create-dirfd-20261017`. Ingen ändring av den aktiva VENTUNO-installationen.

## Manuell granskning i två pass

**Pass 1 – logik/flöde:** `SelfDevPromotionManager._promote_impl` hade en sekvens `target.exists()` → `_sha256(target)` → `shutil.copy2(target, backup)` → `_sha256(backup)` → `_sha256(target)`. Den tog alltså backup via en **ny pathname-öppning**, och beräknade baseline separat från de bytes som faktiskt kopierades. Ett fil- eller katalogbyte mellan kontrollerna kunde ge en avvikande backup, och en föräldersymlänk kunde leda kopieringen utanför projektet. En upptäckt mismatch avbröt innan PREPARED-journalen skrevs, men den otillåtna läsningen kunde redan ha skett.

**Pass 2 – säkerhet/prestanda:** En ny `_copy_verified_backup(source,destination)` öppnar alla föräldrar med `_pinned_parent` (`O_DIRECTORY|O_NOFOLLOW`) och öppnar källfilen relativt redan öppen källkatalog med `O_NOFOLLOW|O_NONBLOCK`. `fstat` kräver en vanlig fil utan extra hårdlänkar. Backupnamnet skapas exklusivt i en **öppen** destinationskatalog via `O_CREAT|O_EXCL|O_NOFOLLOW`, med privata behörigheter. SHA-256 uppdateras direkt från varje block som samtidigt skrivs, så backupens hash alltid motsvarar kopierat innehåll. Storlek, `mtime_ns` och `ctime_ns` kontrolleras före/efter överföringen. Fil och destinationens katalog synkas innan funktionen returnerar; en upptäckt felkopiering försöker radera den ofärdiga backupfilen via samma directory-fd. Normala rwx-bitar från aktiv fil bevaras, men inte privilegierade specialbitar eller xattrs.

Efter genomförd kopiering läser `_hash_existing_regular_path(target)` aktivt filnamn igen via säker no-follow-föräldrakatalog för att upptäcka källändringar före journalens PREPARED. Det tidigare separata pathname-baserade `shutil.copy2`-flödet ersätts; ett befintligt syntetiskt lagringsfelsprov uppdateras så att det injicerar fel i nya hjälpfunktionen.

### Fem nya race-/integritetstester

1. Namnet byts till extern symlänk efter källfilens öppning: backupens bytes och hash matchar original inode.
2. En tillåten förälderkatalog byts till extern symlänk före öppning: kopieringen nekas.
3. Backupens katalogalias byts efter exklusiv filöppning: skrivning sker i redan öppnad legitim katalog, extern fil oförändrad.
4. Aktiv källfil ändras under själva kopieringen: upptäckt ändring avvisas och ofullständig backup tas bort.
5. Redan existerande källsymlänk avvisas innan backup skapas.

## Öppna risker – NO-GO för release

- Snapshot och journal är inte atomiska mot en icke-samarbetande **lokal process med skrivrätt**; källfil kan ändras efter den avslutande rehashkontrollen, eller en redan öppen katalog flyttas av behörig process. Den globala advisory-locken skyddar endast samarbetsvilliga writers.
- `_safe_backup_path`, `_verified_backup`, `_backup_verified_snapshot` samt fallbackcleanup via `shutil.rmtree` innehåller fortfarande delar av pathname-baserad filhantering. Här är endast **den första skapade backupen** härdad.
- Källfiler har inte explicit maxstorlek/tidsgräns; hårdlänkar/bind mounts, UID-behörigheter, stora kataloger, fsync vid verklig strömförlust, journalens HMAC-nyckel och backupverifieringens proveniens kräver fortsatta revisioner.
- Ingen main merge, produktions-promotion, fysisk NPU/ljudtest eller utrullning. Full manuell filrevision och beroende-/licens-SBOM är inte klara.

**Verifieringskrav:** alla regressionsprov och full ARM64 source-only projektsvit på exakt PR-slut-SHA, inga fel.
