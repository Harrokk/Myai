# MyAI – selfdev-säkerhet vid källkopiering och snapshot-hash (2026-10-17)

**Bas:** DRAFT PR #276, `45c8e269e8c1565248bfb12cc67645da6a79f570`. **Gren:** `dev/manual-audit-selfdev-source-snapshot-20261017`. Enbart källkod/source-only-test; ingen ändring av installerad VENTUNO, ljud, kamera, NPU eller modeller.

## Två granskningspass

**Logik:** `SelfDevWorkspace.create` samlade namn med `_iter_source_files(project_root)`, kopierade med `shutil.copy2(source,destination)` och öppnade *sedan* samma namn igen via `_sha256(source)`. Den lagrade baseline representerade alltså en andra läsning, inte nödvändigtvis de bytes som kopierats till staging. Ursprunglig tillåten uppsättning är rotens särskilda filer samt `core/modules/tests/scripts/config/docs/firmware`, men inte `runtime/.git/.venv/__pycache__`.

**Säkerhet:** Med en samtidigt skrivande lokal process kunde ett filnamn eller en mellankatalog bytas till en symbolisk länk mellan katalogenumerering, kopiering och hashning. En kopia kunde då inkludera byte från ett otillåtet mål. Även utan symlänk kunde bytes som kopierades skilja sig från bytes som senare hashades.

## Implementerad avgränsad fix

- `create()` anropar `_stage_source_files()` som öppnar betrodd projektrot och nyskapad staging-rot med Linux `O_DIRECTORY|O_NOFOLLOW`.
- Rekursiv uppsättning görs via `os.scandir(open_dir_fd)`; varje tillåten källfil och underkatalog öppnas sedan **relativt samma öppna katalogdescriptor** med `O_NOFOLLOW`. Symboliska länkar och specialfiler ignoreras vid enumerering; en sen länkändring vid öppning leder till fel, inte extern kopiering.
- En enda öppen filbeskrivare levererar lästa byte. `sha256.update` tar **exakt dessa byte** medan de skrivs till ett nytt exklusivt staging-mål via `os.open(..., O_EXCL|O_NOFOLLOW, dir_fd=...)`. Ingen andra pathname-baserad hashning av source används.
- `fstat` kräver vanlig fil och kontrollerar storlek, `mtime_ns` och `ctime_ns` före/efter kopiering; ändring som upptäcks under kopiering avvisas. Kort skrivning eller noll framsteg avvisas.
- Vanliga rwx-behörigheter inklusive exekveringsbit bibehålls, men setuid/setgid/sticky och utökade filattribut överförs inte av staging. Tillfälliga filer skapas med restriktiva behörigheter, filbytes fsync:as.
- Nya offline-tester: samma bytes i stage + baseline utan andra källhashning; symlänkbyte före open; filnamn ompekat efter open; skrivning till källfil mitt under kopieringen; befintlig symlänk till katalog; bevarad exekveringsbit.

## Begränsningar och öppna risker

- `fstat` före/efter fångar många men inte alla samtidiga ändringar. En kapabel lokal angripare kan potentiellt manipulera en fil under samma tidsfönster och återställa observerad metadata. Därför är detta **inte** ett atomärt snapshot av ett fientligt modifierat filsystem; filesystem snapshot eller immutable Git-objekt och körning mot en betrodd snapshot behövs för fullstark proveniens.
- Om staging misslyckas mitt i kopieringen kan den privata session-katalogen innehålla *delvis kopierade filer*; `session.json` skapas först efter lyckad kopiering, men det krävs egen sanerings-/återupptagningspolicy. Saknat session.json ska aldrig räknas som färdigt.
- `source_drift()`, `build_manifest()`, sessionsmetadata och `verification.json` har fortfarande path-based operationer och behöver egen granskning.
- `_allowed_relative_path` och source-root-föräldrakatalogerna måste bedömas tillsammans med filsystemrättigheter; innehållssignering och oberoende releasegodkännande är separata spärrar.
- Inga övriga delar av selfdev eller dess kör-/deploypolicies påstås vara härdade. Fullständig fil-för-fil-granskning, dependency/SBOM, nativa ABI/licenser, fysisk röst/NPU och rollback återstår.
- Alla ändringar ligger kvar som **DRAFT/NO-GO** för main och aktiv installation. Kräver grön fullständig ARM64 source-only CI på exakt PR-slut-SHA.
