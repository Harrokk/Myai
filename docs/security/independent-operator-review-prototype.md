# MyAI – signerat separat operatörsintyg för verifieringsnyckelrotation

**2026-10-18. Bas:** DRAFT PR #340, exakt HEAD `f0ac08c50bffa2802cc2665787ad5d57b5d5c0c0`. **Status:** testprototyp, ingen produktionsauktorisation, **NO-GO**.

## Granskningspass 1 – vad som återstod

PR #339 krävde dubbla Ed25519-signaturer från befintlig och föreslagen verifieringsnyckel och jämförelse med en oberoende godkänd hash. PR #340 testade SQLite-kandidatens generation, återkallelser och behovet av en separat kontrollpunkt för anti-rollback. Båda tog godkänd rotations-hash som **anroparens argument** och kunde därför inte kryptografiskt skilja en riktig separat administratörsnyckel från ett godtyckligt värde inskickat av MyAI-runtime. Dessutom får användarens uttryckliga mänskliga godkännande aldrig förväxlas med en korrekt signatur från ett hypotetiskt operatörssystem.

## Granskningspass 2 – ny separat kontrollmodul

`core/selfdev_operator_signed_review.py` är en ren verifierare. Den tar **en separat, utanför MyAI förankrad** 32-byte publik Ed25519-operatörsnyckel och **en annan, redan pinnad verifieringsnyckel** från anroparens betrodda konfiguration. Operatörsnyckeln får inte vara identisk med den gamla eller den föreslagna nya verifieringsnyckeln. De publika nycklarna får aldrig väljas från det inskickade intyget.

Operatörsintyget har ett exakt, domänseparerat signeringsschema i maximalt 3072 byte:

- Unik versions- och syftesdomän för *offline review*, aldrig promotion.
- Ett från betrott håll känt enhets-ID, inte ett användar- eller nätverkshärlett plats-ID.
- SHA-256 över det **exakta kanoniska rotationsförslaget**, bundet till dess gamla och nya publika nyckelfingeravtryck och generationer.
- En oberoende, förväntad 128-bitars engångsutmaning från administratör/uppdaterare.
- Kort giltighetstid, högst 300 sekunder.
- En riktig Ed25519-signatur med den separat pinnade **operatörsnyckeln**.

Först efter giltig operatörssignatur, matchat enhets-ID, betrodd utmaning och giltig tid skickar koden den **operatörssignerade** exakta hash-summan som `independently_approved_payload_sha256` till PR #339:s redan granskade `inspect_rotation`. Där kontrolleras de gamla och nya verifierar-Ed25519-signaturerna samt den fullständiga rotationskontexten. Resultatet jämförs mot operatörsintygets gamla/nya generation och fingeravtryck innan något kvitto får lämnas tillbaka.

Detta hindrar en osignerad MyAI-process från att själv välja godkänd rotations-hash och hindrar förväxling mellan enheter, nyckelroller eller ändrade nyckelfingeravtryck. Alla tre nycklar som används i testerna genereras tillfälligt **enbart i testkoden**. Negativa tester omfattar dubbelnycklar, dålig signatur, annan enhet/nonce, ändrade generationer, utgången tid, överlånga JSON, duplicerade fält, annan publik operatörsnyckel, verifierar-/operatörsrollblandning och ett ensidigt signerat verifierarförslag.

`OperatorReview` är ett fryst, **icke-auktoriserande** resultat. Den visar att tre Ed25519-signaturer från två skilda roller och den nya nyckeln stämmer, men har alltid `independently_authenticated_human_intent_verified=False`, `durable_operator_nonce_consumption_verified=False`, `independent_checkpoint_advanced=False`, `verifier_signing_key_activated=False`, `authorizes_mutation=False` och `production_deployment_authorized=False`. Den uppdaterar aldrig SQLite-kandidaten från PR #340 och kopplar inte in `SelfDevPromotionManager`.

## Kvarvarande säkerhetsblockeringar

1. **Separat operatörsidentitet saknas på riktigt.** Ingen betrodd administrativ inloggning, fysisk bekräftelse, skyddad signerare, extern godkännandetjänst, policy för delegation eller incidenthantering är implementerad. Även giltig Ed25519-signatur visar nyckelinnehav, inte att användaren faktiskt godkände bytet.
2. **Nyckelprovisionering och monotont checkpoint-register saknas.** Det finns ingen produktionsoperatörsnyckel eller skyddad administrativ kanal till VENTUNO. En signerad nonce som inte är betrott förbrukad och registrerad kan spelas upp inom tidsfönstret. SQLite-kandidaten kan rullas tillbaka om den separata kontrollpunkten också återställs.
3. **Ingen automatisk produktions-promotion.** Att all kryptografi verifierar testdata får aldrig skapa, ersätta, radera, signera, installera eller köra MyAI-produktionskod.
4. **VENTUNO och äldre GitHub-runner:** faktisk process-UID/ACL, GitHub-runnergrupp, historiska självvärdade workflows, fysisk hårdvara och eMMC-strömavbrott är ännu inte verifierade, migrerade eller åtgärdade. Inga tidigare frysta workflow-hashar eller historiska grenar ändras.

**Acceptans för denna DRAFT:** fullständig GitHub-hostad ARM64-svit grön på exakt sista commit. Det är källkodsverifiering, inte releasebeslut. Ingen ändring på `main`, VENTUNO, runner, nycklar eller installation.
