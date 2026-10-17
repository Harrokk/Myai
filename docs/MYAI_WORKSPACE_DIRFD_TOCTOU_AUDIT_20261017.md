# MyAI – race-härdning av workspace-I/O (källkodskandidat, 2026-10-17)

**Bas:** DRAFT PR #273 `301a9b7e7545db2a046abb9c1f4f0c9888ce4297`. **Ny gren:** `dev/manual-audit-workspace-dirfd-toctou-20261017`. Ingen produktionsinstallation, sammanslagning eller fysisk hårdvaruoperation.

## Fynd FILE-RACE-01: path-check/open och mkdir/replace

Före ändringen arbetade läsning så här: `resolve_workspace_path()` följde och validerade symlänkar, `path.is_file()` kontrollerade typen och `path.open()` öppnade senare sökvägen igen. En annan process med skrivbehörighet i katalogen kunde därför byta slutfil eller föräldrakatalog mellan kontroll och användning. Även skrivningen använde den återuppslagna absoluta föräldersökvägen för `mkstemp` och `os.replace`, vilket gav en potentiell omdirigering av skrivning om förälderkatalogen ersattes.

## Ändring: Linux dir_fd + O_NOFOLLOW, default fail-closed

- Ny `_safe_parts()` avvisar tomma komponenter, `.`, `..`, absoluta och NUL-innehållande namn utan att lita på sökvägsupplösning.
- `_anchored_parent()` öppnar workspace-roten och varje underkatalog med `O_DIRECTORY | O_NOFOLLOW`. För skrivning skapas underkataloger via `os.mkdir(..., dir_fd=...)` och öppnas på samma vis.
- Läsning öppnar **slutfilen relativt redan öppnad förälderkatalog** med `O_NOFOLLOW | O_NONBLOCK`; `fstat()` kräver vanlig fil före streaming. FIFO och symboliska slutlänkar avvisas.
- Skrivning kontrollerar filtyp utan att följa symlänkar, skapar en exklusiv slumpad temporär fil med `os.open(..., dir_fd=...)` och ersätter målnamnet via `os.replace(..., src_dir_fd=..., dst_dir_fd=...)`. Det sista steget följer inte en sent insatt mållänk. Vid fel rensas den temporära filen genom samma fd.
- Befintliga gränser för filändelser, `write_enabled`, audit-logg och teckenavkortning bibehålls.
- Plattformar utan dessa säkra POSIX-funktioner får ett fel i stället för en tyst återgång till sökvägsbaserad öppning. Detta gäller bl.a. Windows och kräver separat säker implementationsväg inför Windows-stöd.

## Regressionstester (utan nät/hårdvara)

Sex nya syntetiska tester i `tests/test_file_workspace.py` provar (1) slutlänk redan närvarande, (2) slutlänk byts precis före läs-öppning, (3) förälderlänk byts precis före katalogöppning, (4) förälderns sökvägsalias byts efter fd-öppning men före atomär replace, (5) FIFO avvisas utan blockering, (6) `../`, `./` och dubbla sökvägsseparatorer avvisas. Tre äldre tester justeras: läsningens blockstorlek, atomär rename och disk-full-felinjektion flyttas till motsvarande descriptor-baserade gränser. Kör full source-only ARM64-pytest på **exakt sista commit**, och häv inga release-spärrar vid enbart syntetiskt grönt resultat.

## Öppna begränsningar (NO-GO)

- Stöd för Windows-workspace-I/O behöver separat säkert filsystemsgränssnitt. Detta Linux-först-förslag ska inte användas som Windows-produktionslösning.
- `workspace_root(settings)` och dess överordnade kataloger måste komma från betrodd konfiguration och skyddas av OS-behörigheter. Koden är inte en mount-namespace-/process-sandbox: en aktör med rätt att flytta redan öppna kataloginoder till en annan sökväg kan påverka den faktiska platsen; fd förhindrar däremot ompekning via en ny symlänk.
- Kataloglistning i `list_workspace_files()` använder fortfarande pathname/stat-race; den är inte omfattad av denna read/write-fix.
- `core/selfdev_workspace.py`, Excel-/kamera-/GPS-verktyg och `core/deployment_lock.py` har andra filvägar och skyddas **inte** automatiskt av denna ändring.
- Hårdlänkar, ACL/mountändringar, specialfilsbeteenden, max filstorlek/CPU-tid och lokala fysiska attacker kräver separat granskning och test.
- Komplett rad-för-rad-granskning av varje projektfil, nativ dependency/SBOM/firmware/licenser, fysisk mikrofon/TTS/NPU/HTP, återställning och releaseprövning återstår.

**Revisionsstatus:** källkodsfix för två read/write racefönster, inte komplett FS-isolering; DRAFT/NO-GO för main och produktion.
