# MyAI – no-follow för workspace-rötter, manifest och driftkontroll (2026-10-17)

**Bas:** DRAFT PR #307, SHA `6506413d00b35af454cd51e8fb137384267e2d1b`. Endast kod i GitHub och isolerade, source-only ARM64-tester. Ingen aktiv selfdev-promotion, rollback eller installation.

## Granskningspass 1 – dataflöde och fynd

PR #307 säkrade nya sessionskatalogers skapande och initial staging genom öppnade katalogbeskrivare. Äldre existerande workspaces läses och ändras emellertid också av `SelfDevWorkspace.write_text()`, `build_manifest()`, `_hash_allowed_relative()` och `_stage_source_files()`. Dessa använde `os.open(full_path, O_DIRECTORY|O_NOFOLLOW)` för sina startkataloger. På Linux skyddar `O_NOFOLLOW` **endast slutkomponenten** i en full pathname; ett utbytt `runtime/selfdev/session` eller en utbytt projektkatalog i ett tidigare led kan därför omdirigera öppningen trots att underliggande traversal av `core/*.py` är dirfd-säkrad.

`build_manifest()` gjorde dessutom en separat `exists/is_symlink`-kontroll före sin katalogöppning, vilket gav ett ytterligare fönster för namnbyte. `_session_directory_fd()` hade redan en manuell säkrad loop; den kan återanvända en gemensam funktion.

## Granskningspass 2 – genomförd härdning

- Ny hjälpfunktion `_open_directory_nofollow(root)` kräver en absolut lexikal sökväg utan `..`. Den öppnar `/` och varje enskild katalogkomponent med `O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC` relativt en öppnad förälderkatalog; filbeskrivare stängs på alla felvägar.
- `write_text()` öppnar sin workspace-root genom hjälpfunktionen innan underkataloger skapas eller filer skrivs.
- `build_manifest()` tar bort den separata pathname-preflightkontrollen och öppnar katalogroten direkt med hjälpfunktionen. En **saknad** valfri rot ger fortsatt tomt manifest, medan en symlänkad eller annan ogiltig katalog avvisas.
- `_hash_allowed_relative()`, som används för upptäckt av ändringar från sessionsbaslinjen, öppnar sin projektrot utan att följa något förälderalias.
- `_stage_source_files()` öppnar även projektroten säkert; när funktionen inte får en pinnad destinationsfd öppnas också workspace-roten säkert. Det pinnade sessionsskapandet från PR #307 är fortfarande kvar.
- `_session_directory_fd()` återanvänder gemensam no-follow-öppning, utan att ändra lagringsformat eller API för sessionsmetadata.
- Fem offline-regressioner: skrivarens sessionrot byts efter målpreflight; manifestets sessionroot byts vid öppning; skillnad mellan saknad rot och symlinkad rot; en hashkontrollerad projektroot byts efter metadatahämtning; projektsrot byts till symlänk före staging.
- Full ARM64 source-only körning ska också återverifiera befintliga tester av metadata, staging, symlinkade barnkataloger, promotion, rollback och recovery.

## Kvarstående NO-GO

- `_candidate_path()` använder fortfarande `Path.resolve()` för en kompatibel, icke-auktoritativ preflight; **inga filer skrivs efter enbart denna kontroll** utan den nya descriptorbaserade kontrollen. Den bör granskas separat för preflightens semantik, resursgränser och möjliga förvirrande fel.
- En privilegierad/icke-samarbetande lokal skrivare kan fortfarande byta *katalognamn efter att en inode öppnats* eller bryta advisory locking med en ny lock-inode. Denna PR skyddar mot omdirigerade uppslagningar, men är inte en global atomisk filesystem-snapshot.
- Komplett fil-för-fil-granskning, beroenden/SBOM/licenser/ABI och fysiska VENTUNO-tester (ljud, NPU, faktiskt strömavbrott och recovery) återstår. Ingen merge till main, ingen aktiv installation. Alla PR:er förblir DRAFT.

**Grind:** fullständig GitHub Actions ARM64 source-only CI på exakt sista SHA.
