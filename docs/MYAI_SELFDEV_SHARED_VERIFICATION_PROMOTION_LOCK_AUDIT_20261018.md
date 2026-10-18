# MyAI – samma projektlås för sandboxverifiering och selfdev-promotion
**Datum:** 2026-10-18 · **Bas:** verifierad DRAFT PR #318, commit `a4184af616e8246849e5fd33c850f766c65a659f` · **Utförande:** isolerad GitHub-hostad ARM64, ingen aktiv VENTUNO-ändring

## Pass 1 – flöde och risk

Efter PR #318 ogiltigförklaras ett gammalt `verification.json` vid start av en ny verifiering. Samtidigt finns redan det projektgemensamma, icke-blockerande OS-låset `runtime/selfdev/.promotion.lock`, som skyddar selfdev-promotion, rollback och recovery mellan samarbetsvilliga processer. **Sandboxverifieringen använde inte det låset.** Därför kunde en promotion/rollback påbörjas medan verifieringen körde sina separata kommandon, eller en verifiering börja samtidigt som en promotion kontrollerade sessionens tidigare godkännande. Även med stabila filbeskrivare och manifestkontroller är detta en farlig kontrollflödesrace mellan verifieringsbeslut och aktiv koduppdatering.

## Pass 2 – begränsad implementation

- De befintliga, granskade rutinerna för att validera/skapa den privata selfdev-katalogen och öppna/validera/exklusivt låsa `.promotion.lock` flyttas till två **gemensamma modulfunktioner** i `core/selfdev_promote.py` som tar `workspace`. De behåller exakt `O_DIRECTORY|O_NOFOLLOW`-ankring, ägare-/behörighetskontroller, filtyp/nlink-kontroll, `flock(LOCK_EX|LOCK_NB)` respektive Windows msvcrt-väg och säker upplåsning.
- `SelfDevPromotionManager._private_selfdev_directory` och `_project_mutation_lock` behålls som kompatibla wrappers, så tidigare promotion-/rollbacktester och granskad filhantering fortfarande använder **samma lås-inode**.
- `SelfDevVerifier.verify()` håller **samma projektlås** från före ogiltigförklaring av föregående verifiering, genom staged manifest- och källkontroller, alla Bubblewrap-kommandon, post-run-driftkontroll och tills ett nytt `verification.json` publicerats. Om låset redan innehas av promotion/rollback misslyckas verifieringen omedelbart utan att starta sandbox eller ta bort tidigare godkännande.
- Tre nya regressionstester täcker att en pågående verifiering blockerar promotionslåset i varje sandboxkommando; en redan låst promotion blockerar verifiering före ogiltigförklaring och exekvering; ett verifieringspreflightfel frigör låset.
- Inga ändringar i JSON-protokoll, godkännandefraser, staging-allowlist, sandboxens rättigheter eller HMAC-journal görs.

## Kvarstående säkerhetsgränser (NO-GO)

- `flock` är **rådgivande** och koordinerar bara processer som använder samma riktiga lock-inode. En separat same-UID/privilegierad skribent som kringgår låset kan fortfarande flytta kataloger eller skriva filer. Projektnamn/UID måste isoleras på operativsystemsnivå; låsning skyddar inte mot en osamarbetsvillig användare med full filsystemsåtkomst.
- Verifieringens resultatfil har fortfarande inte oberoende, kryptografiskt attesterad proveniens från en separat skyddad verifieringstjänst. JSON-integritet och sammanhängande kommandoprotokoll ska **inte** beskrivas som kryptografisk verifieringssäkerhet.
- Exekvering av syntetiska tester sker endast på en disponibel GitHub-hostad ARM64-runner enligt isoleringen i PR #316, inte på `ventuno-q` med produktionens användarrättigheter.
- Komplett fil-för-fil-/beroende-/SBOM-/licens-/native ABI-granskning, fysisk NPU/ljud och verkliga avbrotts-/återställningstester kvarstår. PR:n förblir DRAFT utan merge till main eller installation.

**Verifieringskrav:** komplett source-only ARM64 CI på exakt sista HEAD och dokumenterat testresultat.
