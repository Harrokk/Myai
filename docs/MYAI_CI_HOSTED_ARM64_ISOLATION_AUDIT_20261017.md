# MyAI – blockerande CI-isolering: bort från aktiv VENTUNO-användare (2026-10-17)

**Bas:** grön DRAFT PR #315 `b68ae2249d8552aee4d0fe3ca842c367e755187f`. Enbart ändring i GitHub-workflow och revisionsdokumentation. Ingen runner-service, installerad MyAI-kod, befintlig aktiv VENTUNO-venv eller main-branch ändras i denna DRAFT-PR.

## Pass 1 – konkret hotmodell och upptäckt

Tidigare `.github/workflows/tests.yml` hade `runs-on: [self-hosted,Linux,ARM64,ventuno-q]` och kontrollerade uttryckligen `id -un = arduino`. Workflow hämtade visserligen exakt SHA i `$RUNNER_TEMP/myai-ci-source`, men körde sedan `compileall`, hela Python-`pytest`-sviten och ett Pythonbaserat static-audit-script med `/home/arduino/MyAI/.venv/bin/python`, på samma fysiska maskin och under samma UID som den aktiva MyAI-installationen.

**Detta är ingen teknisk sandlåda.** Python-tester och källkod på en utvecklingsgren har i princip samma fil- och processrättigheter som `arduino`-kontot. En komprometterad testfil, körbar import eller pip-/pytest-kod kan därför läsa/skriva data och installationsfiler som användaren kan nå, även om dess aktuella arbetskatalog är temporär. Den tidigare formuleringen ”Run full test suite without modifying live installation” var en **avsikt**, inte en säkerhetsgaranti. Det finns inga belägg i denna revision för att sådana filer faktiskt har ändrats, men den tidigare CI-arkitekturen kan inte användas som bevis på isolerad testning.

## Pass 2 – ändring och kontroll

- Flytta **det ordinarie fullständiga källkodstestflödet** till `runs-on: ubuntu-24.04-arm`, som är en GitHub-hostad ARM64-runner i en separat temporär VM. GitHub dokumenterar att dessa runners finns för både publika och privata repositories.
- Lägg först en **fail-closed** kontroll: `runner.environment == github-hosted` och `uname -m == aarch64`. Ett oavsiktligt återbruk av self-hosted runner ska stoppa jobbet innan någon repositorykod exekveras.
- Behåll `permissions: contents: read`, SHA-verifierad git-hämtning och en tillfällig checkout. GH_TOKEN finns endast i hämtsteget.
- Skapa en **ny isolerad Python-venv i GitHub-runnerns `$RUNNER_TEMP`**, och installera de publicerade minimikraven plus specifika versioner av `pytest` och `cryptography` med `--only-binary=:all:`. Använd enbart denna interpreter i kompilering, statisk revision och fullständig testsvit.
- Avlägsna alla användningar av `/home/arduino/MyAI/.venv/bin/python` samt det självvärdade runnerkravet från detta workflow. Låt separata fysiska VENTUNO-workflows fortsätta vara separat klassade som hårdvarutester med egna riskgrindar.
- Förtydliga workflow-namn, concurrency-grupp, jobbsteg och GitHub Actions-sammanfattning så att testresultaten inte kallas ”på VENTUNO” när de körs på en GitHub-hostad ARM64-VM.
- Resultatet måste verifieras i **ett faktiskt GitHub-hostat ARM64-jobb på exakt PR-HEAD**, inklusive hela repo-testsviten. Att bara syntaktiskt validera YAML räcker inte.

## Kvarstående release-NO-GO

- Detta ändrar **bara `tests.yml` på den aktuella grenen**. Äldre utvecklingsgrenar och andra självhostade `ventuno-*.yml`-workflows kan fortfarande köra kod på det fysiska kortet. De måste inventeras och granskas separat för triggers, behörigheter, skrivrättigheter, API-token och fysiska sidoeffekter.
- Kod som körs på GitHub-hostad ARM64 är **inte** en fysisk validering av Qualcomms NPU, QAIRT-drivrutiner eller VENTUNO:s ALSA/USB-ljud. Sådana tester behöver ett särskilt, säkerhetsavgränsat hardware-CI-konto/runner med explicit godkännande.
- Venv-installation av `requirements.txt` använder ännu versionsintervall och är **inte ett komplett reproducerbart, hash-pin:at beroendelås**. Leveranskedja, licenser, SBOM, native ABI och wheelproveniens kräver fortsatt granskning.
- Statuskontrollernas namn och runnerresurser kan påverka branch protection och GitHub-minutkvoter; före framtida merge ska repositoryns faktiska skyddsregler och GitHub-plan verifieras.
- Fysisk återställning efter strömavbrott, all kod- och beroenderevision, autentiserad selfdev-verifieringsproveniens och verkliga VENTUNO-stresstester är fortfarande öppna blockerare. Denna PR är **DRAFT/NO-GO** tills hostad CI är grön och säkra triggers är granskade.

Referens: https://docs.github.com/en/actions/reference/runners/github-hosted-runners

**Ingen live-installation eller fysisk åtgärd körs av denna ändring.**
