# MyAI – de fyra arbetsflödena som bara finns på main

**Källrevision:** main `f125fe6dc9abd6b27747f86d440fbb77b0602e58` jämförd med DRAFT-stacken fram till #239.

**Beslut:** INGEN automatisk main-merge och ingen kopiering av äldre workflows till testgrenen. De ska först ersättas eller migreras till en **exakt SHA-låst, tillfällig checkout** som inte skriver i /home/arduino/MyAI.

| Arbetsflöde enbart på main | Kontroll | Integrationsbeslut |
| --- | --- | --- |
| `.github/workflows/ventuno-full-dev-validation.yml` | Fetch av historiska `dev/routing-boundary-followup` i temporär katalog utan att verifiera aktuell PR-commit. Fulla tester är isolerade, men saknar aktuellt source SHA. Genererar systemd-enheter under tempkatalog. | Ersätt branch-fetch med exakt HEAD, jämför med aktuella DRAFT-kontroller och behåll endast säker checkout-/cleanupkod. |
| `.github/workflows/ventuno-integration-validation.yml` | Gammal fastlåst GenieX-integrationscommit; kan starta endast från main; använder `GITHUB_WORKSPACE` på self-hosted runner och genererar unitfiler. | För framtida integration krävs ny commit-identitet, isolering och korrekta unit-verifieringar, inte reaktivering av stale job. |
| `.github/workflows/ventuno-regression.yml` | **Hög risk före merge:** Kör tester i `/home/arduino/MyAI`, kör `python -m py_compile` och `scripts/generate_ventuno_systemd.py` på installerad programkatalog, inte temporär checkout. Workflown är manuell och main-begränsad; ingen oönskad aktuell körning har konstaterats. | **Ta inte in i integrationskandidaten oförändrad.** Ersätt med exact-SHA disponibel worktree och strikt source-only/test-only; ingen produktionsfil får skrivas. |
| `.github/workflows/ventuno-runner-check.yml` | Workflow_dispatch, endast kontroll av runneridentitet; rapporterar sökväg/runnernamn i CI-logg. | Funktionellt överflödigt bredvid moderna metadata-only gates; sanitera utskrifter om den behålls. |

## Fysiskt testbeslut

Dessa fyra saknas från DRAFT-branchens filsnapshot men finns på main. `main` och DRAFT är **divergerade**, därför räcker det inte med att grön PR-branch CI förutsäger grön `main` efter merge.

**P0 inför framtida full release:** gör först en separat integrationsbranch med genomgång av de fyra jobben och ett `main`-sammanförande som inte startar installerade program eller fysiska hårdvarumoment. **Kör sedan helt nya x86- och ARM64-tester på exakt integrations-SHA.**

**Ingen** sammanslagning, driftsättning, systemd-installation, ljudanrop, NPU-exekvering eller modifiering av `main` utfördes i denna granskning.
