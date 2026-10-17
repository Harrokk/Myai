# MyAI – manuell granskning av selfdev staging write TOCTOU, 2026-10-17

**Bas:** DRAFT PR #275, `d4a427198c728535934790d7eac081fbea3dacfb`. **Ny gren:** `dev/manual-audit-selfdev-write-dirfd-20261017`. Endast källkod och syntetiska tester, ingen installering av aktiv MyAI.

## Två granskningspass

1. **Logik/kontrakt:** `SelfDevWorkspace.write_text` kallar `_candidate_path`, skapar förälderkatalog med `Path.mkdir`, skapar exklusiv temporär fil med `tempfile.mkstemp(dir=target.parent)`, kontrollerar sökvägen igen, och kör `os.replace(temporary, target)`. Den raderar `verification.json` efter godkänd skrivning. Säkerhetsgränserna är en allowlist för relativa källsökvägar samt symlänkskontroller.
2. **Säkerhet/effekter:** Alla pathname-baserade kontroller och användningar sker vid olika tidpunkter. En lokalt skrivbehörig process kan byta en underkatalog till symlänk efter den sista kontrollen men före `os.replace`; därmed kan skrivningen riktas mot en extern målsökväg. En sen målsymlänk är i sig inte lika farlig vid atomär `rename`, men katalogkomponenterna är kritiska. Inget här förutsätter någon aktiv nätverkstjänst.

## Kodfix
- `write_text()` behåller befintlig lexikal allowlist/`_candidate_path` för att avvisa otillåtna skrivmål.
- Workspace-root och nya/återanvända underkataloger öppnas med `O_DIRECTORY|O_NOFOLLOW`; nya kataloger skapas enbart via `os.mkdir(..., dir_fd=...)`.
- Målinoden kontrolleras utan att följa symlänkar; endast befintlig **vanlig fil** eller frånvarande mål accepteras. En andra kontroll sker direkt före bytet.
- Temporär fil skapas exklusivt och slumpmässigt i den öppna kataloginoden med `O_EXCL|O_NOFOLLOW`; både `os.replace` och felfallsstädning använder `dir_fd` och relativa namn.
- Originalbeteendet att invalidera verification-snapshot efter lyckad skrivning behålls.
- Om säkra Linux/POSIX-funktioner saknas avbryts operationen (inget tyst osäkert Windows-fallback).

## Nya simulerade tester
- Förälderkatalog byts till symlänk före `open` och får inte skriva till extern katalog.
- Förälderkatalogens alias byts **efter** att fd öppnats men **före** `replace`; bara den öppnade ursprungskatalogen får ändras.
- Slutfilen byts till symlänk precis vid `replace`; extern symlänkdestination förblir oförändrad.
- Specialfil FIFO avvisas och tidigare verification-snapshot behålls.
- Befintliga regressioner för tillåtna filer, otillåtna mål, misslyckad rename, drift och metadata måste fortsatt passera.

## Kvarstående NO-GO
- `SelfDevWorkspace.create()` använder fortfarande källindexering via `rglob()`, `shutil.copy2(source, destination)` och efterföljande `_sha256(source)` där källnamnet kan bytas av en lokal aktör med filsystemrättighet. Den läs-/kopieringsgränsen är **inte** löst av denna patch och är nästa högriskmål.
- `build_manifest()`, `source_drift()` och `metadata()/verification_path.unlink()` använder fortfarande pathname-baserad I/O med särskilda frågor om atomäritet och symlänkar. Ett returnerat Path-objekt är en **namnreferens**, inte ett tidsstabilt bevis för vilken inode som skrevs.
- Session-root, källkodsträd, filsystembehörigheter och användare med möjlighet att flytta redan öppnade inoder måste omfattas av en separat deployment/OS-policy.
- Full manuell granskning av varje repo-fil, full SBOM/ABI/licenser, fysisk ljud/NPU-testning, oberoende rollback och produktionsrelease är alltjämt **inte** färdiga. Ingen merge till main eller installation.
- Kräv full ARM64 source-only CI på exakt **sista** commit. Ett tidigare grönt test från parent-grenen är inte tillräckligt.

**Status:** avgränsad kodfix och regressionsunderlag; inte komplett selfdev-sandbox.
