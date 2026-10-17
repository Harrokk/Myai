# MyAI – skapande och kontroll av privata selfdev-kataloger (2026-10-17)

**Bas:** PR #289 vid `e72e2661f9445545095a528ad12f3a56f1a90841`. **Gren:** `dev/manual-audit-selfdev-private-directory-dirfd-20261017`. Enbart DRAFT och isolerad source-only-testning. Ingen installerad VENTUNO-fil eller aktiv självmodifiering ändras.

## Pass 1 – kodflöde och konstaterat fynd

`SelfDevPromotionManager._private_selfdev_directory(create=True)` användes av OS-projektlåset och journalens HMAC-nyckel. Den kontrollerade `runtime.is_symlink()` och `selfdev.is_symlink()`, gjorde sedan `directory.mkdir(parents=True)`, och kontrollerade efteråt katalogtyper/UID/permissions via `is_dir`, `is_symlink` och `lstat`. Alla operationerna gick via nya pathname-uppslagningar; mellanliggande namn kunde bytas till länkar mellan preflight, skapning och kontroll. Även om PR #288–289 nu förankrar själva nyckeln och låsfilens slutliga I/O fanns fortfarande ett separat fönster under katalogskapandet.

## Pass 2 – implementerad fix

- `_private_selfdev_directory()` öppnar projektets förälderkataloger via `_pinned_parent(directory,create=create)` med `O_DIRECTORY|O_NOFOLLOW`; ett oväntat symlänksbyte i `runtime` leder till PermissionError i stället för att trädet följs.
- Den **öppnade** runtime-katalogens inode valideras via `fstat` för katalogtyp, UID och avsaknad av grupp-/världsskrivning.
- Vid `create=True` skapas endast `selfdev` via `os.mkdir(name,mode=0700,dir_fd=runtime_fd)`, eller en redan existerande katalog kontrolleras. Ingen öppning genom absolute pathname används för det ledet.
- Selfdev-katalogen öppnas via `os.open(name,O_DIRECTORY|O_NOFOLLOW,dir_fd=runtime_fd)`; UID/permissions läses från öppnad fd och slutnamnet stat:as no-follow relativt runtime-fd för att upptäcka om filnamnet bytts efter öppningen. `create=False` skapar inget.
- Fem nya regressionstester: föräldern `runtime` byts till symlänk, `selfdev` byts till symlänk före öppning, `selfdev` byts efter öppning, osäkra permissions i runtime avvisas, och read-only kontrolldrift skapar inga integritetsnycklar.
- Tidigare säkerhetstester för globala låset, nyckel-HMAC, journaler, backup, rollback och recovery körs också på ARM64.

## Gränser och NO-GO

- En icke-samarbetande process med rätt att flytta projektets runtime-träd efter sista alias-kontrollen kan fortfarande bryta samordning över olika kataloginoder; detta skydd är inte en kernel-garanterad atomär lock-path-namespace.
- Den operation som skapar saknade **föräldrar** i `_pinned_parent(create=True)` är descriptorbaserad, men dess ägarskapskontroller på tidigare projektkomponenter är fortfarande drifts- och UID-beroende. Full verifiering kräver isolerad process-user och privat projektroot.
- `SelfDevWorkspace.create`, `_safe_backup_path`, recovery-inventering, förberedda backup-kataloger och felstädning har egna filsystemvägar att granska; denna PR hävdar inte att hela selfdev-flödet är säkert.
- Slutlig release kräver fullständig fil-för-fil- och beroendegranskning (inklusive nativ SBOM/licenser), fysisk VENTUNO/NPU/ljud-testning och verifierad rollback vid strömavbrott. Alla ändringar förblir **DRAFT/NO-GO** för main och installerad MyAI.

**Verifieringskrav:** fullständig ARM64 source-only CI på exakt sista commit. Ingen aktiv promotion eller återställning.

