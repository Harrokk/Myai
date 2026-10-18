# MyAI – operatörsintyg med SQLite-engångsutmaningar: källkodsgranskning

**Datum:** 2026-10-18. **Bas:** DRAFT PR #341, HEAD `59299a9360bba0bb015769b4b5340d92f8e1b7be`.

**Status:** endast testprototyp, **produktion NO-GO**. Ingen installation, ingen administrativ signeringstjänst, ingen självutvecklingspromotion.

## Pass 1: den faktiska återspelsluckan

PR #341 ger en strikt separat Ed25519-operatörssignatur över det exakta dubbelsignerade verifierarnyckelbytet, knutet till enhet, generation och en operatörsutmaning. Den har inte ett eget beständigt register som bevisar att operatörsutmaningen utfärdats av rätt tjänst eller förbrukats. En giltig signerad post kan därför återanvändas under giltighetsfönstret om anroparen återbrukar samma nonce utan skyddad tillståndshantering. PR #340:s SQLite-kandidat för nyckelgenerationer täcker **inte** denna operatörsutmaning separat.

Ett korrekt signerat operatörsintyg är **inte** en faktisk mänsklig autentisering eller ett bevis på att en specifik person tryckte godkänn. Ingen autentiserad operatörstjänst eller signerande produktionsnyckel har driftsatts.

## Pass 2: genomförd testimplementation

`core/selfdev_operator_nonce_ledger.py` accepterar en redan öppnad separat SQLite-anslutning. Den öppnar inga filer, har inga privata nycklar, startar inga processer och anropar aldrig `SelfDevPromotionManager`.

`issue_operator_review_challenge` genererar 128-bitars slumpmässig nonce med `secrets.token_hex(16)` som standard. Endast för deterministiska tester kan `nonce_factory` injiceras. Kandidattabellen binder varje nonce till separat angiven betrodd enhet, verifierarnyckel + exakt generation, den föreslagna nya nyckelns SHA-256, SHA-256 för exakt rotationsförslag, operatörens separat pinnade offentliga nyckelfingeravtryck och högst fem minuters livslängd. Nonce är en unik primärnyckel; dubletter blockeras.

`consume_operator_review_once` använder `BEGIN IMMEDIATE`, hämtar först den redan upplagda betrodda kontexten, avvisar okänt/förbrukat/för gammalt nonce och kräver att aktuella betrodda verifierar- och operatörsnycklar samt enhets-ID matchar databastillståndet. Därefter körs PR #341:s `inspect_operator_review`, vilket kräver **tre** rätt signerande Ed25519-nycklar (operatör, befintlig verifierare, ny verifierare), giltig nonce, enhet, SHA-256 för rotationsförslaget och förväntat tidsfönster. Först efter denna kontroll sker `UPDATE ... WHERE consumed_unix IS NULL` följt av commit. Fel eller konkurrerande användning ger rollback.

Ett extra **anroparlevererat** `independently_consumed_nonces` kan användas för att stoppa ett känt gammalt nonce **även om SQLite-databasen återställts från snapshot**. Modulen är tydlig med att den **inte** genererar, skyddar, lagrar eller avancerar ett sådant verkligt externt checkpoint-register.

`tests/test_selfdev_operator_nonce_ledger.py` använder temporära SQLite-filer och engångs-Ed25519-testnycklar. Tester täcker:

- Giltig engångsinspektion utan rätt att byta nyckel eller installera kod; återanvändning nekas.
- Stängning/återöppning av SQLite med fortsatt förbrukad utmaning.
- Två samtidiga SQLite-anslutningar där bara en får förbruka en given utmaning.
- Ogiltiga signaturer för operatören eller någondera verifieringsnyckeln, annan enhet, nonce, rotationsdigest, nyckel, generation, utgången tid, okänd nonce, nonce-kollision och felaktiga checkpoint-format; ingenting får delvis commit:as.
- **Konkret rollback-demonstration:** en databaskopia från innan förbrukningen avvisas när ett **separat och korrekt avancerat** kontrollunderlag säger att nonce redan förbrukats. Samma gamla kopia *kan* åter acceptera nonce med en felaktigt tom/gammal extern lista – ingen falsk anti-rollback-garanti lämnas.

Returtyperna `PendingOperatorReview` och `InspectedOperatorReview` har permanent `authorizes_mutation=False`, `production_deployment_authorized=False`; dessutom anger det lyckade läskvittot `independent_human_approval_verified=False`, `external_rollback_checkpoint_advanced=False` och `verifier_key_activated=False`.

## Produktionsblockerare

1. **Oberoende autentiserad administrativ kanal** och skyddad operatörs-Ed25519-nyckel på eller utanför enheten saknas. Att signaturerna verifieras betyder endast nyckelinnehav.
2. **Externt beständigt, monotont anti-rollback-register** för operatörsutmaningar och PR #340:s nyckelgeneration finns inte. En komprometterad fysisk fil, enhet eller rollbackad kontrollpunkt kan kringgå kandidatmodellen.
3. VENTUNO:s faktiska verifierar-/updater-/runner-UID, systemd, Linux-ACL, processgrupper, GitHub runner-groups, fem kända äldre källkodsexponeringar och historiska workflows är inte kontrollerade eller säkrade i produktion.
4. Verklig NPU, mikrofon, USB, Bluetooth, eMMC-strömförlust, återhämtning, fullständig MyAI-testplan, källproveniens och SBOM/ABI kvarstår.
5. **Inget anslutet promotionsflöde:** testmodulen får inte starta verklig nyckelrotation, kodmodifiering, självutveckling eller fysisk runner-jobbkörning.

**DRAFT-acceptans:** fullständig GitHub-hostad ARM64-svit på exakt slutlig HEAD ska vara grön. Ingen merge till `main`, ingen VENTUNO-ändring eller produktionsgodkännande.
