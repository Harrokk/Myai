# MyAI – oberoende signering av syntetiskt vittneskvitto (testmiljö)

**Datum: 2026-10-19. Bas: DRAFT PR #346, HEAD `60a2e2131b8f13da5e6a11f4904f2ceb6ac5730a`. STATUS: ENDAST TESTPROTOTYP. PRODUKTION NO-GO.**

## Pass 1 – vilka tidigare förtroendegarantier saknades?

PR #346 verifierar två separata Ed25519-signaturer och journalens exakta händelsedigest, men skapar inte ett kvitto från en **fristående signerande process som själv kontrollerar en källa**. Ett svagare genomförande skulle kunna be MyAI-runtime skicka `passed=true` tillsammans med en påhittad hash och få det signerat. Då verifierar alla senare komponenter bara en kryptografiskt signerad lögn.

## Pass 2 – testimplementation och negativ kontroll

`core/selfdev_receipt_issuer_preview.py` kan **endast** härleda ett kvittounderlag från en redan öppnad separat kandidatjournal och en giltig, mot pinnad genesis/aktuell head verifierad Ed25519-vittneskedja. Den tar inte emot signerad framgång, output-skript, kommandon, filvägar eller kvittofält från klienten. Den godkänner endast journalens två uttryckligen bevittnade stadier `operator_witness_recorded` och `key_witness_recorded`, kontrollerar nonce och verifierarepoch, och kräver att gammal verifierarnyckel ligger i den signerade spärrlistan efter rotation. Modulen signerarar inte själv och öppnar inga filer eller socketar.

`scripts/test_disposable_receipt_issuer.py` kör ett faktiskt **värd-Linux UID-/Unix-socket-integrationstest** på en särskild GitHub-hostad Ubuntu-testmaskin. Testets rotprocess skapar två syntetiska, Ed25519-signerade vittnesposter och en signerägd SQLite-kandidatjournal. Filkatalogen ägs av UID 23006 (0700) och de syntetiska datafilerna har 0600. Signeraren släpper alla grupper/privilegier och byter till UID 23006 **innan** den genererar en egen flyktig privat Ed25519-signernyckel som aldrig serialiseras.

Unix-socketen görs avsiktligt åtkomlig för alla för att själva `SO_PEERCRED`-kontrollen ska prövas. MyAI-runtime (UID 23002) och CI (UID 23003) nekas. En uppdateraridentitet (UID 23001) som skickar ett extra `passed=true` nekas av det strikta IPC-formatet. För en tillåten anropsutmaning **läser signeraren själv** sin privata syntetiska vittnesfil och SQLite-journal, verifierar den signerade kedjan mot den redan pinnade offentliga testnyckeln och huvudhashen och konstruerar kvittot endast från detta. Först därefter signeras kvittot med den egenägda privata nyckeln. Den andra förfrågan med samma nonce nekas inom **samma signerprocess**. Till sist kontrolleras kvittosignaturen och journalbindningen även av PR #346:s ordinarie `inspect_signed_witness_milestone`.

Den tillfälliga roten distribuerar de offentliga testnycklarna via testprocessens minne och en pipe. Detta är **inte** någon produktionsprovisionering. Ingen signering av verkliga MyAI-filer eller verklig eMMC-skrivning sker.

`.github/workflows/disposable-independent-receipt-issuer.yml` kör endast på GitHub-hostad `ubuntu-22.04`, med kontrollerad `runner.environment=github-hosted`, exakt commit-SHA, läsbehörighet för GitHub-token, tillfälligt venv och en **snäv lista** över publika testmoduler som får läsas av test-UID. De privata signerdata ligger i ett annat katalogträd. `sudo` används enbart för att skapa de **flyktiga testidentiteterna på den hostade VM:n** och används inte på VENTUNO. Vanliga ARM64-source-only pytest kör inga UID-byten eller socketar.

## Avgörande återstående begränsningar

1. **Det här bevisar ingen verklig skrivhändelse på fysisk VENTUNO.** Rotprocessen förbereder den syntetiska vittneskedjan och den syntetiska journalen. Signerarens kryptografiskt verifierade kvitto bevisar att den observerade *testkällan* överensstämmer, inte att en autentiserad extern vittnestjänst i produktion faktiskt utfört en lagringscommit.
2. **Ingen beständig replay-databas i signeraren.** Den vägrar återanvändning av nonce i samma testprocess, men en omstart eller rollback av tillståndet skulle kunna skapa nytt signeringsfönster. Extern signerägd replayhistorik och monotont färskhetsankare måste skyddas oberoende.
3. **Ingen bevisad oberoende produktionstilldelning av UID/nyckel.** På VENTUNO återstår säker OS-UID/ACL/systemd- och GitHub-runnergranskning, signerägd lagring, tillförlitlig nyckelbackup, rotation, anti-rollback och installatörens signering.
4. **Inget säkert produktionsbeslut.** Den nya datatypen har `independently_observed_external_write=False`, `independently_protected_fresh_head_proven=False`, `automatic_recovery_authorized=False`, `authorizes_mutation=False`, `production_deployment_authorized=False`. PR #346:s verifieringskvitto håller fortsatt samma NO-GO.
5. **Ingen fysisk validation:** NPU, ljud, Bluetooth, eMMC-strömavbrott, riktig full MyAI-testplan och specifika historiska GitHub-runner-exponeringar kräver ytterligare kontroller.

**DRAFT-acceptans:** hostad fullständig ARM64-projektsvit + separat hostad Linux-UID/IPC-körning skall vara grön på exakt samma slutliga commit. Ingen `main`-merge och ingen fysisk VENTUNO-åtgärd.
