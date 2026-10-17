# MyAI – skrivskyddad staging under Bubblewrap-verifiering (2026-10-17)

**Bas:** DRAFT PR #312, exakt SHA `6a75ed0daf01f82056ef732e1ff90a229398638f`. Denna ändring berör endast GitHub-källkod och syntetisk source-only ARM64-testning, **inte** den installerade VENTUNO-processen.

## Pass 1 – säkerhetsfynd och flödeskontroll

`SelfDevVerifier._sandbox_command()` bygger ett `bwrap`-kommando med `--unshare-all`, privat `/dev` och `/tmp`, samt readonly systemkataloger. Men stagingkatalogen `/workspace` monterades med **`--bind`**, alltså med skrivåtkomst. Detta gör det möjligt för testkod eller en komprometterad beroendemodul som körs under verifieringen att ändra stagingfilerna själva. PR #312 gör välbehövliga kontroller av manifest och aktiv källkod **efter** testkörningen, men en temporär ändring som återställs till identiska bytes innan efterkontrollen upptäcks inte. Därför ska den miljö som kör testerna inte ha skrivrätt till koden den kontrollerar.

En andra funktionell risk är att `python -m py_compile /workspace/...` uttryckligen skriver `.pyc`, trots `PYTHONDONTWRITEBYTECODE=1`. Att bara ändra till `--ro-bind` utan att flytta Python-kachen kan få normala valideringssteg att misslyckas.

## Pass 2 – avgränsad säkerhetsändring

- Ändra den enda staging-mounten från `--bind PROJECT_STAGE /workspace` till **`--ro-bind PROJECT_STAGE /workspace`** i den gemensamma `_sandbox_command`, så både syntaxkontroller och pytest är skrivskyddade.
- Behåll `--unshare-all`, `--die-with-parent`, `--new-session`, privat `--dev /dev`, `--proc /proc`, och `--tmpfs /tmp`.
- Lägg till `PYTHONPYCACHEPREFIX=/tmp/myai-pycache`, `XDG_CACHE_HOME=/tmp/myai-cache` och `PYTEST_ADDOPTS=-p no:cacheprovider` i sandboxmiljön. `py_compile` skriver då bytekod till det privata temporära filsystemet i stället för till testad stagingkod; pytest undviker den vanliga katalogcachen i workspace.
- Befintligt `PYTHONDONTWRITEBYTECODE=1` och `HOME=/tmp` behålls.
- Regressioner kontrollerar att **samtliga genererade kommandon** har readonly workspace-mount, ingen rw-mount, samt att temporära filer hänvisas till privat `/tmp`.
- Ingen aktivering av live selfdev, ingen ändring av metadata-/journalformat och ingen merge till main.

## Kvarstående release-NO-GO

- Dessa tester verifierar konstruerade `bwrap`-argument. De är **inte** bevis för att riktig Bubblewrap på VENTUNO har startat en read-only sandbox som kan köra projektets verkliga testsvit. Det kräver ett separat isolerat **fysiskt runtime-smoketest**, särskilt om vissa tester normalt skriver direkt till arbetskatalogen i stället för `/tmp`.
- `bwrap_path` och `python_executable` är inställbara, och `command_runner` kan injiceras i tester. Ett korrekt format på `verification.json` plus summerade returvärden är **inte kryptografiskt ursprungsbevis** för en riktig sandboxkörning; man får inte ta bort denna NO-GO-grind förrän proveniens-, process- och UID-isolation bedömts.
- En skrivbehörig lokal angripare kan byta stagingkatalogalias före `bwrap` öppnar sin bind-källa, även om MyAI:s metadata- och hashflöden återvaliderar som skyddslager. Beteendet runt sådan aliasväxling kräver fortsatt manuell kod- och driftgranskning.
- Komplett fil-för-fil-granskning, beroenden/SBOM/licenser/nativ ABI, fysisk ljud/NPU-verifiering och strömavbrotts-/återställningstester på VENTUNO återstår.

**Grind:** full ARM64 source-only GitHub Actions på exakt slutlig SHA. Även grön CI medger inte deployment.
