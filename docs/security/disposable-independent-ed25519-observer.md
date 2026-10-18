# MyAI — fyrrollsgranskning av oberoende Ed25519-verifiering och engångsregister

**Datum:** 2026-10-18. **Bas:** DRAFT PR #335, `271afc39a903ecfc33459fb62a18fa58b0018c52`.

**Status: KONTROLLERAT DEMONSTRATIONSTEST. INTE EN PRODUKTIONSVERIFIERARE. NO-GO.**

## Pass 1: fortsatt säkerhetslucka

PR #333 verifierar signerade Ed25519-resultat, PR #334 visar ett SQLite-register för engångsutmaningar och PR #335 testar en separat Linux-UID med `SO_PEERCRED` och ett falskt HMAC-test. Dessa kan var för sig vara korrekta men bevisar inte tillsammans att en fristående verifierare har utfört observationen själv, hållit nyckeln hemlig och lämnat ett resultat som uppdateraren inte kan spela upp igen.

Särskilt viktigt: en signatur över en JSON-post med `passed=True` är **inte bevis för att ett visst test faktiskt kördes**. Signeraren måste själv styra testplan, indata och sandbox samt granska autentiska resultat; annars kan den bli en signeringsorakel åt en angripare.

## Pass 2: separat testprototyp med verkliga Linux-UID

`scripts/test_disposable_ed25519_observer.py` demonstrerar en sammanhängande kontrollkedja med **fyra skilda numeriska Linux-UID** under en engångscontainer:

- **CI (23003)** och **runtime (23002)** får inte läsa verifierarens 0700-katalog och 0600-markerfil; deras Unix-socketanslutningar avvisas genom kernel-`SO_PEERCRED`.
- **Updater (23001)** skapar ett slumpmässigt 128-bitars nonce och en uppdaterarägd SQLite-databas med privaträttigheter. Den har ett test-betrott offentligt Ed25519-nyckelvärde mottaget genom en temporär pipe från testrotprocessen och väntar på verifierarens signatur.
- **Verifieraren (23004)** genererar en egen ny privat Ed25519-nyckel **efter byte av UID**; den lagras **endast i processminnet**, inte i Git, Docker-lager eller fil. Endast en ofarlig textmarkerfil skrivs under 0600 för att illustrera rättigheter. Verifieraren läser sin egen syntetiska, fixerade Python-fil `SAFE = 1`, kontrollerar bytes och ägare och kör därefter själv en fast `python -I -B -c`-subprocess som använder `ast.parse` och SHA-256, utan att exekvera källfilens kod. Verifieraren kontrollerar exitstatus/stdout/stderr mot förväntad observation innan signering.
- **Signatur och återspelskontroll:** verifieraren bygger en fast, kanonisk Ed25519-post knuten till nonce, session, syntetiskt manifest, testplan och resultatdigest. Uppdateraren verifierar signaturen mot testnyckeln och förbrukar noncen atomiskt enligt PR #334. Samma signerade svar avvisas efter både omedelbar återanvändning och stängning/återöppning av SQLite-databasen. En updaterförfrågan med extra `passed=True` avvisas av protokollet.

**Avgörande begränsning:** den syntetiska JSON-posten använder `sandbox: bubblewrap` enbart som en **testetikett** för att utöva det befintliga schemaflödet i PR #333–334. Det faktiska demonstrationsprovet kör **inte Bubblewrap**, utan en fast Python-syntaxkontroll inuti nätverksisolerad Docker. Det är alltså medvetet **inte ett autentiskt Bubblewrap-verifieringsbevis** och får aldrig användas som ett sådant. Testresultatet innehåller uttryckligen `test_only_signature_has_synthetic_bubblewrap_flag: true` och `real_bubblewrap_evidence_proven: false`; produktionens verifierar-/promotionsväg är inte kopplad till denna modul eller dess nyckel. En signerare som skulle utfärda denna etikett i produktion vore osäker.

## GitHub-miljön

`.github/workflows/disposable-independent-ed25519-observer.yml` kör enbart på GitHub-hostad x86_64 Ubuntu med explicit `runner.environment=github-hosted`, read-only GitHub-token och exakt `GITHUB_SHA`. På den temporära GitHub-maskinen hämtas bara binära `cryptography==45.0.7`-hjul och beroenden. Sedan installeras de **utan nätverk** från en read-only mount inuti en `python:3.12-slim-bookworm`-container pinnad till tidigare använd digest. Containern har `--network none`, `--read-only`, ny temporär `/tmp`-tmpfs med `exec` enbart för att kunna ladda native-modulerna i det offline installerade kryptografibiblioteket, CPU-/minnes-/PID-gränser, `no-new-privileges` och endast `CHOWN/FOWNER/SETUID/SETGID` som Linux-förmågor. Endast fem snävt avgränsade källfiler/hjulkataloger monteras read-only. VENTUNO:s kod, GitHub-hemligheter, fysiska ljud/NPU-enheter, befintliga installationskataloger och Docker-socket monteras aldrig.

De nedladdade hjulen är versionsbegränsade men saknar ett separat, källgranskat hash- och utgivarintyg; ett lyckat paketinstalleringssteg får inte misstas för slutlig SBOM/proveniensgranskning. Containerdigest bevisar identitet för de hämtade lagren, inte hela leverantörskedjans tillförlitlighet.

`tests/test_disposable_ed25519_observer_source.py` innehåller separata källkodstester utan root, `fork`, lokal `setuid`, socket- eller Docker-körning. Fullständiga ARM64-sviten kör även dessa.

## Vad är fortfarande inte uppnått?

1. **Oberoende riktig Bubblewrap-verifiering:** verifieraren ska i framtiden själv skapa och observera en fullständig, deterministisk testplan i verklig isolering utan att kunna välja `passed` från klientdata.
2. **Produktionsnyckel och nyckelrotation:** en verifierarägd privat signeringsnyckel, pinnad publik nyckel distribuerad genom ett betrott administrativt förfarande, skyddad nyckelbackup och säker återkallning saknas fortfarande. Testets publika nyckelpipe är inte produktionsprovisionering.
3. **Faktiska uppdateringsbehörigheter:** kontrollerad IPC, updater-ägt persistent engångsregister, autentiserad källproveniens, signerade byggartefakter och mänskligt godkännande återstår, liksom eMMC-kraschåterhämtning.
4. **VENTUNO-runnern:** historiska självhostade GitHub-workflows och deras möjlighet att använda `arduino`-UID är ännu inte administrativt spärrade eller fysiskt verifierade.
5. **Fullständiga hårdvarutester och release:** ljud, mikrofon, NPU, Bluetooth, strömavbrott, dependency/SBOM/ABI, rollback och driftsättning måste granskas separat.

**Resultatet i denna PR ska ses som en väl avgränsad integrationsdemonstration, inte som ett bevis att produktions-promotion blivit säker. DRAFT, ingen `main`-merge, ingen fysisk runner eller VENTUNO har ändrats.**
