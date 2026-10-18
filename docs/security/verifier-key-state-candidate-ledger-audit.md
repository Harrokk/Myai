# MyAI – beständigt kandidatregister för verifieringsnycklar, generationer och återkallelse

**Datum:** 2026-10-18. **Bas:** DRAFT PR #339, commit `0f3d2c91c1773ed76ac4cbc257a639ac9d543529`.

**Status: OFFLINE SQLite-PROTOTYP. INGEN AKTIV PRODUKTIONSNYCKEL ÄNDRAD. NO-GO.**

## Pass 1 – bekräftad lucka

PR #339 kontrollerar dubbelsignerad Ed25519-nyckelrotation, gammal och ny nyckel, operatörsnonce, generation och en separat godkänd SHA-256 för rotationsförslaget. Allt är avsiktligt **inspektion utan nyckelbyte**. Det förra arbetet saknade en testad modell för att hantera generationer och spärrade nycklar under omstart och samtidiga försök. En äldre SQLite-snapshot kan dessutom återinföra en redan återkallad nyckel om alla trust anchors lagras i samma fil.

**Kärnkravet:** Minst en oberoende förtroendekälla måste innehålla den *aktuella* exakta nyckeln, generationen **och hela den förväntade återkallelselistan**. En signerad post eller SQLite-fil som MyAI-runtime själv kan ändra är inte en oberoende källa.

## Pass 2 – genomförd kandidatimplementation

`core/selfdev_verifier_key_state_preview.py` hanterar **bara en särskilt namngiven kandidat-datamodell**, inte produktionens aktiva nycklar. Alla SQL-operationer går via en **redan öppnad, separat tillhandahållen SQLite-anslutning**. Koden öppnar ingen fil, skapar inga Linux-användare, genererar inga nycklar, signerar inga bevis, kör inget program, aktiverar ingen nyckel och anropar aldrig promotion.

Tre kandidattabeller används: `candidate_verifier_state` (en enda aktiv **kandidat**-epoch och publik nyckel), `candidate_verifier_revoked` (pensionerade fingeravtryck) och `candidate_verifier_transitions` (unika, tidigare prövade generationsbyten och operatörsnonces). Testbootstrap kräver en separat given `TrustedVerifierKey` och nekar dubbla eller osäkra återstarter.

Vid varje `inspect_candidate_snapshot` måste databasens nyckelbytes, SHA-256-fingeravtryck, generation och **hela** spärrlistan stämma med den exakta `independently_pinned_checkpoint` som anroparen har lämnat från en annan betrodd källa. Matchande fingeravtryck men saknade återkallelser ger **blockering**, inte ett grönt svar.

Vid `simulate_candidate_transition` används `BEGIN IMMEDIATE` i en enda SQLite-transaktion. Nuvarande kandidat jämförs mot den separat pinnade kontrollpunkten, därefter körs PR #339:s dubbelsignatursgranskning med betrodd nonce och oberoende angiven godkänd payload-hash. Först därefter skrivs en **simulerad** nyckelgeneration, föregående nyckel pensioneras och en unik händelse registreras. CAS-villkor på gammal nyckel/generation och primärnycklar på historik motverkar dubletter och samtidiga skrivningar. Felaktig signatur, datum, nonce eller generation ger `ROLLBACK`, inte delvis förbrukat tillstånd.

Returtyperna `CandidateSnapshot` och `CandidateTransition` anger alltid `actual_key_rotation_performed=False`, `production_deployment_authorized=False` och `authorizes_mutation=False`. En lyckad kandidattransaktion är **inte** ett nytt betrott verifieringsankare. Den fristående kontrollpunkten måste uppdateras genom en separat auktoriserad och skyddad process, som **inte finns i denna PR**.

`tests/test_selfdev_verifier_key_state_preview.py` använder tillfälliga SQLite-filer och tillfälliga Ed25519-testnycklar och omfattar bland annat:
- korrekt kandidatövergång epoch 4→5, pensionering och återläsning efter stängning/ny anslutning;
- gammalt förslag och gammal signatur avvisas efter övergång;
- två samtidiga anslutningar kan inte båda registrera samma övergång;
- ändrad SQLite-nyckel, saknad spärrlista, ogiltig signatur, nonce, felaktig operator-hash och utgången tid avvisas utan partiell SQL-commit;
- **verklig rollback-demonstration:** en kopia av SQLite-filen från epoch 4 upptäcks av en **ny separat** kontrollpunkt som förväntar epoch 5. En *gammal* kontrollpunkt för epoch 4 missar däremot rollbacken, vilket dokumenterar exakt varför SQLite inte ensamt bevisar anti-rollback.

## Allvarliga återstående blockerare

1. **Ingen fysisk anti-rollback:** en SQLite-transaktion eller `PRAGMA synchronous=FULL` gör inte en databas motståndskraftig mot en attackerare med samma UID, full filsystemsåtkomst, rollbackade backups, eMMC-strömförlust eller komprometterad root. En skyddad, oberoende monoton kontrollpunkt krävs för VENTUNO, och dess lagring, distribution och uppdatering måste utformas och testas separat.
2. **Ingen riktig administratörsautentisering:** ett `independently_approved_payload_sha256`-argument är ännu inte bevis för faktiskt, separat administratörsgodkännande. En komprometterad anropare kan skicka vilket hashvärde den vill. Den skarpa administrationskanalen och särskild incidentåterkallelse/frysning saknas.
3. **Ingen produktionsinstallation eller provisioning:** fysisk verifierar-UID, skyddad signeringsnyckel, GitHub runner-groups, ACL:er, systemd-enheter och nyckelrotation är oförändrade.
4. **Ingen koppling till produktionens selfdev-promotion:** hela inspektionskedjan förblir avsiktligt isolerad och kan inte godkänna koduppdatering. Hela testplanen inklusive beroenden, SBOM, native ABI, NPU, ljud, Bluetooth och strömavbrott är inte fysisk verifierad.
5. **Historiska arbetsflöden:** minst fem äldre källkodsgrenar med självhostad `ventuno-q`-användning är fortfarande dokumenterade; GitHubs administrativa runnerkontroll är ännu inte verifierad.

**Acceptans för denna DRAFT:** exakt slutlig commit skall ha grön fullständig GitHub-hostad ARM64-svit. Utfallet bekräftar enbart kandidatdatabasens logik. Ingen `main`-merge, ingen VENTUNO-runnerdispatch, ingen installerad tjänst eller ny produktionsnyckel.
