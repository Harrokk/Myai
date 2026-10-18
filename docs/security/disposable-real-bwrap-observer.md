# MyAI: verklig Bubblewrap-observation och icke-auktoriserande signerat testbevis

**Datum:** 2026-10-18. **Bas:** DRAFT PR #336, commit `5b2c85fc420c473da75662e25a2a50f9e047bc9f`.

**Status: KÄLLKODS-/HOSTAT LABBTEST, ALDRIG VENTUNO-PRODUKTIONSVERIFIERING.**

## Första granskningspasset – luckan efter PR #336

Den tidigare fyrrollsdemonstrationen testade riktiga Linux-UID, Ed25519 och SQLite anti-replay, men den framgångsrika verifieringsposten angav `sandbox=bubblewrap` trots att endast ett AST-test kördes i Docker. Detta var tydligt dokumenterat som syntetiskt, men det är inte ett verkligt bevis för isolerade sandboxtester. Utan en faktisk Bubblewrap-körning och observation av dess skydd får en signering aldrig betraktas som verifierad.

## Andra granskningspasset – det här testet

`core/selfdev_bwrap_observation.py` är en strängt avgränsad observationsfunktion för en **lokal, förtroendeägd syntetisk testfil**. Den accepterar inte kod, kommandon, tillåtna paths eller positiva resultat från MyAI-runtime. Den bygger alltid en fast Bubblewrap-kommandorad med `--die-with-parent`, `--new-session`, `--unshare-all`, `--clearenv`, isolerad `/proc` och `/dev`, skrivbar privat `/tmp`, enbart read-only systemkataloger och en read-only-montering av exakt testkatalog på `/workspace`. Ingen osandboxad fallback.

Inne i **faktiskt Bubblewrap** läser en fixerad Python-process den syntetiska `fixture.py` och gör endast `ast.parse` och SHA-256. Den provar att skriva till read-only-originalfilen, vilket måste misslyckas, och läser den egna nätverksnamnrymdens inode via `/proc/self/ns/net`. Värdprocessen jämför inoden mot sin egen (måste skilja sig), kräver strikt heltalsreturkod noll, tom stderr, begränsad stdout, exakt fältformat och väntad källhash. Detta bevisar en faktiskt startad sandbox med skild nätverksnamnrymd och skrivskyddad fixture **i just den hostade testmiljön**, under förutsättning att Linux-kärnan och Bubblewrap fungerar enligt dokumenterade semantiken.

`scripts/test_hosted_real_bwrap_observer.py` får bara köras när `MYAI_HOSTED_BWRAP_TEST=yes`, `MYAI_RUNNER_ENVIRONMENT=github-hosted` och processen inte är root. Den skapar en tillfällig testfil, kräver att `observe()` lyckas, genererar sedan ett temporärt Ed25519-testnyckelpar, använder en SQLite-engångsutmaning och verifierar att signatur och anti-replay fungerar även efter återöppning. Den skapar **ingen privat produktionsnyckel**, läser inga verkliga MyAI-filer, använder inga fysiska enheter och gör ingen kodändring.

Workflow `.github/workflows/disposable-real-bwrap-observer.yml` kör endast på GitHub-hostad `ubuntu-22.04`, med `contents: read`, exakt `GITHUB_SHA`, temporärt virtuellt Python-miljö och versionsbegränsat `cryptography==45.0.7`. Den installerar Bubblewrap via vanliga Ubuntu-paket på en *disposable hosted VM* men ändrar **inte** någon global AppArmor- eller userns-sysctl och går aldrig över till körning utan Bubblewrap. En miljö som nekar skapandet av skyddade namnrymder ska ge blockerad/fallerad testkörning, inte grönt test. Testernas kärnlogik täcks dessutom med mock-only ARM64-pytest för ogiltigt namespace, skrivbart arbetsområde, falska hashvärden, drift, ogiltiga kommandon och uteblivet Bubblewrap-stöd.

## Säkert begränsad evidens

- Den här testintegrationen körs under **ett hostat testkonto**, inte i en separat produktionsverifierar-UID. Den illustrerar verklig Bubblewrap-observation, men **inte** fullständig produktionsprocessisolering.
- Ett temporärt Ed25519-nyckelpar i testsamma process kan inte räknas som betrodd produktionsproveniens. Nästa säkerhetssteg måste ge den separata verifieraren från #335–336 egen verklig Bubblewrap-körning och betrodd nyckeldistribution, utan klientstyrda testresultat.
- Ett godkänt syntetiskt AST-test bevisar **inte** fullständig MyAI-testplan, kodgranskning, dependency/SBOM/ABI, ändrad originalkod, hårdvarukompatibilitet, NPU/ljud/Bluetooth eller fysisk strömavbrottsåterhämtning.
- Detta kopplas inte till `SelfDevPromotionManager`. `production_deployment_authorized` och `selfdev_promotion_authorized` är alltid false. Ingen `main`-merge, VENTUNO-runnerdispatch, systemd-ändring, konto- eller hemlighetshantering på enheten.
- PR #330:s fem dokumenterade äldre branch-exponeringar och den självhostade GitHub-runnerns otillräckliga åtskillnad kvarstår. Revisionsspärren och NO-GO gäller tills GitHub-administrationsåtgärder och fysisk granskning gjorts.

**Tester måste verifieras på samma exakta sista commit:** fullständig GitHub-hostad ARM64-svit och separat faktisk Bubblewrap-körning på tillfällig GitHub-hostad Linux. Inget ska sägas vara tekniskt godkänt om Bubblewrap-delen stoppas av hostens AppArmor/userns-policy eller annat testfel.
