# MyAI – två äldre source-audit-workflows flyttas från produktions-VENTUNO
**Datum:** 2026-10-18 · **Bas:** verifierad DRAFT PR #319, commit `25fb58056e018b4b3dcc32113c4aed9631690235`

## Pass 1 – inventering och konkret risk

Under granskningen av `.github/workflows/` hittades två jobb med en onödig exekveringsgräns: `ventuno-full-project-two-pass-audit.yml` (andra ARM64-steget) och `ventuno-static-repository-audit.yml`. Båda kunde triggas via `push` på **specifika historiska utvecklingsgrenar**; endast tvåpassrevisionen hade dessutom `workflow_dispatch`. Båda hade `runs-on: [self-hosted, Linux, ARM64, ventuno-q]`. De hämtade och körde Python-skript från vald källkodscommit i temporära arbetskataloger, men gjorde det med den verkliga VENTUNO-runnerns `arduino`-konto. Det innebär att en källkodsgren som används för revision kan exekvera kod nära installerade produktionstjänster, även om jobbens avsikt är read-only. Det fanns även kontroll mot faktisk `/home/arduino/MyAI/.venv` respektive `systemctl is-active`.

Detta är **två bekräftade exponeringar**, inte ett påstående att alla cirka 172 workflowfiler har granskats till samma djup. Skillnaden mellan automatiska triggers och read-only shell-kommandon ska inte misstas för en säker OS-processgräns.

## Pass 2 – kodändringar

- Båda jobbtyperna använder nu `runs-on: ubuntu-24.04-arm` för att utföra källkodsrevisionen i en **disponibel, GitHub-hostad ARM64-miljö**.
- På den hosted runnern kontrolleras uttryckligen `runner.environment == github-hosted` och `uname -m == aarch64` innan källkoden hämtas; SHA hämtas och jämförs mot `GITHUB_SHA` i separata temporära kataloger.
- Koden som använde den installerade VENTUNO-miljön, `/home/arduino/MyAI/.venv/bin/python`, och kontrollen av de aktiva systemd-tjänsterna tas bort från dessa source-only-flöden. De ersätts av rent källkodsbaserad AST/statisk granskning.
- `permissions: contents: read`, exakta SHA-kontroller, publicerad revisionslogg och tillåtna manuella triggers behålls.
- Sex nya automatiska testfall kontrollerar båda workflowfilerna avseende runneridentitet, ingen självvärdad `runs-on`, ingen installerad VENTUNO-åtkomst, endast read-only tokenbehörighet samt explicit exakt SHA.

## Tidigare fryst revisionsbaslinje förblir avsiktligt röd

Den oförändrade filen `config/ventuno_manual_workflow_git_oids_20261016.json` innehåller 103 historiska Git-blob-identiteter. Den är **inte** en godkännandelista och ska aldrig ändras för att en ny workflowändring ska se redan godkänd ut. Efter de tidigare ändringarna av `tests.yml` och denna PR:s tvåpassworkflow stämmer **101 av 103** historiska filer fortfarande med den frysta baslinjen, och de två ändrade filnamnen måste rapporteras explicit. Två befintliga fail-closed-regressioner uppdateras för det nya, avsiktligt blockerade tillståndet (101 respektive 100 matchningar när testet dessutom manipulerar ett tredje OID). Produktionsrelease och main-merge fortsätter vara **otillåtna**.

## Fortsatta spärrar / NO-GO

- **DRAFT-koden är inte aktiverad i main eller andra redan existerande grenar.** Historiska arbetsgrenar med äldre kopior av dessa workflows får inte betraktas som säkrade förrän motsvarande ändringar eller central policy faktiskt tillämpas. En organisationsinställd begränsning av vilka workflöden/refar som får använda runnergruppen är ett starkare skydd.
- Andra manuella och eventuellt automatiskt triggbara workflows som fortfarande hänvisar till självvärdade runners måste inventeras med samma tvåpassmetod. Denna PR ändrar bara de två verifierat riskfyllda källkodsgranskningsjobben.
- Detta är **inte** ett av/på-kommando för VENTUNO, och inga tjänster, runners, behörigheter eller installerade filer på maskinen ändras genom skapandet av en DRAFT-PR.
- Fullständig fil-för-fil- och tredjeparts-/SBOM-/ABI-/licensrevision, oberoende verifieringsproveniens samt fysiska NPU/ljud-/strömavbrotts- och rollbacktester återstår.

**Verifiering:** kör exakt slutlig commit i hela källkodssviten på disponibel GitHub-hostad ARM64. Ingen merge till main eller produktionsdrift.
