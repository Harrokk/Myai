# MyAI — promotion/rollback: fokuserad tvåpassgranskning, 2026-10-17

**Bas:** PR #279 commit `a82e3349c7ebb3922474e4d841a6c3120797cc8e`. **Ändringsgren:** `dev/manual-audit-selfdev-promote-atomic-dirfd-20261017`. Source-only DRAFT, ingen merge eller installation i aktiv MyAI.

## Pass 1: flöde och kontrakt

Full `core/selfdev_promote.py` inventerad genom namngivna funktioner och fördjupad kontroll av `_atomic_copy`, `_source_matches_before_replace`, `_promote_impl`, `_restore_from_backup`, `_backup_verified_snapshot`, `_rollback_impl` och `_recover_interrupted_impl` samt relevanta regressionstester. Promotion är manuell och kräver explicit approval, projektglobalt lås och en journal för återställning. Aktiv källkod kan muteras först när säkerhetskopiering och PREPARED-journal skapats. Återställning försöker undvika att skriva över externa ändringar.

Den äldre `_atomic_copy` skapade tempfil via en pathname, kopierade `source` med `shutil.copy2`, kontrollerade målet via ny path-baserad hashning och gjorde `os.replace(temp,destination)` med en absolut destination. `_promote_impl` jämförde stagingfilens hash med verifierat manifest **före** kopieringen, och kontrollerade målfilens hash **efter** promotion. Detta lämnade en mellanliggande ändrings-/symlänksrace innan säker slutlig rename.

## Pass 2: säkerhet och föreslagen kodfix

1. `_pinned_parent(path)` går från filsystemrot längs varje katalogkomponent med `O_DIRECTORY|O_NOFOLLOW` och `dir_fd`. Öppnad kataloginode används för fortsatta operationer, inte ett alias som kan ompekas med symlänk.
2. `_atomic_copy` öppnar en vanlig källfil med `O_NOFOLLOW|O_NONBLOCK` relativt öppnad källkatalog och skapar en unik temporär målinode med `O_CREAT|O_EXCL|O_NOFOLLOW` relativt öppnad målkatalog.
3. Kopieringen sker i 65 536-byte-block, beräknar SHA-256 från de **bytes som skrivs**, avvisar upptäckta samtidiga storleks-/tidsändringar och validerar en optional `expected_source` **före målfilens ersättning**. Promotion skickar den verifierade `planned_hashes[relative]` till denna kontroll.
4. `_source_matches_before_replace` kontrollerar målfilen via samma öppna målkatalog utan att följa symlänkar. `os.replace(..., src_dir_fd=..., dst_dir_fd=...)` kan inte dirigeras till en annan katalog genom sent symlänksbyte. Vanliga RWX-permissions bevaras; privilegierade specialbitar överförs inte. Fil och öppnad målkatalog fsync:as.
5. Sex offline-regressionstester: källhashfel före rename, sent bytt källsymlänk, bytt målkatalog före öppning, ompekat målkatalogalias före rename, bytt slutfilssymlänk och bevarad exekveringsbit. Existerande backup-, journal-, lås-, rollback- och avbrottstester måste fortsatt vara gröna.

## Gränser som förblir NO-GO

- `_sync_directory(destination.parent)` behålls för bakåtkompatibel durability/fault-injection, men använder en ny pathname-öppning **efter** den descriptor-relativa rename. En privilegierad angripare kan påverka denna extra fsync, även om den inte väljer vilken aktiv kodfil som ersätts. Fysiska strömavbrottstest och crash consistency återstår.
- Journalen `_atomic_write_record`, backupens första `shutil.copy2`, `_verified_backup`, `_safe_project_target` samt deletionen av nytillkomna filer under rollback och flera recovery-vägar använder fortfarande pathname-baserade filoperationer. Dessa kräver separata högprioriterade ändringar. Befintlig projektglobal lock stoppar inte andra icke-samarbetande OS-processer.
- `expected_old` är **inte** en kärnatomär compare-and-swap; icke-samarbetande writer kan ändra målinoden efter kontroll men före rename. Detta bör hanteras med process-/UID-isolering och explicit releasebegränsning.
- En redan öppnad katalog kan flyttas av en lokal skrivrättighetsinnehavare. Dirfd skyddar namnuppslagningar men är inte en mount-/process-sandbox; källträdet måste fortfarande styras av betrodda behörigheter.
- Läsning av stora filer och antal samtidiga promotionobjekt är inte absolut tidsbegränsade. Filnamnskoll kan behöva striktare hantering av atypiska filsystem.
- Granskningsvyn `core/selfdev_review.py` gör ännu path-baserad `read_text` och bygger diff före avkortning. Detta är nästa separata riskfix; den har **inte** lösts i denna PR.
- Full repositoryrevision rad-för-rad, nativa beroenden/SBOM, NPU/ljud, och verkliga deployment/rollbacktest saknas alltjämt. Inget godkännande för promotion i produktion.

**Krav:** full ARM64 source-only CI på exakt sista commit. Håll alla ändringar DRAFT och installerad VENTUNO oförändrad.
