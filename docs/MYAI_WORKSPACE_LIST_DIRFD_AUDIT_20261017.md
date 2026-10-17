# MyAI – kataloglistning och metadata utan symlänksrace (2026-10-17)

**Bas:** PR #274 commit `6ee6b3eb66a4cff3b2cda2f6979f0431e0e07528`. **Ändringsgren:** `dev/manual-audit-workspace-list-dirfd-20261017`. Source-only DRAFT: ingen kod installerad på MyAI, ingen ljud-/modell-/NPU-aktivitet.

## Första granskningspasset: funktionellt flöde
`list_workspace_files` skapade först workspace-root, hämtade `os.scandir(directory_path)`, sorterade varje katalogs DirEntry-objekt, hoppade över initiala symboliska länkar, kontrollerade `path.resolve(strict=True)` och läste till slut `path.stat()` från en sökväg. Detta behöll förvisso antal resultat och rimlig minnesförbrukning per katalog, men upprepade sökvägsuppslagningar efter tidigare kontroller.

## Andra granskningspasset: säkerhet och metadata
En annan process med skrivrätt i workspace kan byta ut en vanlig fil mot en symlänk precis mellan `path.resolve()` och `path.stat()`. Då följer `stat()` symlänken och returnerar potentiellt sekretesskänslig filstorlek från en extern fil, trots att listningsfunktionen aldrig borde gå utanför sitt workspace. Samma problem uppstår för underkataloger om deras namn byts till länkar mellan kontroll och `scandir()`.

### Åtgärdad källa: `modules/files/workspace.py`
- Linux-först: `O_DIRECTORY | O_NOFOLLOW` krävs; annars avbryts listningen utan osäker fallback.
- Workspace-roten öppnas en gång, och rekursiv listning använder `os.scandir(open_directory_fd)`.
- Metadata hämtas via `os.stat(entry_name, dir_fd=open_directory_fd, follow_symlinks=False)`; endast vanliga filer listas.
- Nästa underkatalog öppnas relativt redan öppen katalog med `os.open(..., dir_fd=..., O_NOFOLLOW | O_DIRECTORY)`. En sent bytt symlänk kan inte ge åtkomst till målkatalogen.
- Resultatens relativa namn och filstorlek behålls; alfabetisk ordning och `max_list_entries` bibehålls. En katalog sorteras i taget.
- `contextlib.closing` och `try/finally` stänger generator och fd även vid tidig avslutning.
- Fyra syntetiska tester: sent bytt slutfil, bytt förälderkatalog före öppning, ompekning efter öppning samt fd-städning vid resultatgräns. Ett äldre test justeras för descriptor-baserad listning.

## Kvarstående risker / nästa revisionsmoment
- En fientlig process med rätt att flytta en **redan öppnad kataloginode** kan fortfarande påverka var den finns på filsystemet. Fd-skyddet hindrar symlänksompekning till en annan katalog vid senare uppslagning, men skapar ingen komplett mount-/process-sandbox.
- `workspace_root(settings)` och dess föräldrakataloger är fortfarande en betrodd operatörskonfiguration. Fulla POSIX/ACL-/hardlink-/bindmount-hotmodeller är inte avslutade.
- Listan kan kräva betydande minne för en enda extremt stor katalog; mycket djup rekursion kan ge resursutmattning. Det kräver separat antal-/djup-budget.
- `core/selfdev_workspace.py` har egna `rglob`/`copy2`/`mkstemp`- och source-drift-uppslagningar och är **inte** skyddad av den här ändringen. Självmodifieringsfunktionerna blir nästa avgränsade revisionsmål.
- Fullständig manuell granskning av varje fil, fullständig SBOM och nativa dependency-/licenskontroller samt fysisk verifiering av röst/NPU/rollback återstår. **Main-merge, installation och release NO-GO**.

## Testgräns
Kör syntetiska regressionsfall och full projekt-ARM64 source-only vid exakt slutlig commit. Testernas `tmp_path`-workspace är de enda avsedda filoperationerna; inga skarpa konfidentiella filer eller nätverksadresser behöver läsas.
