# MyAI – extern signerad kontrollpunkt och separat vittneslagring (source-only)

**2026-10-18. Bas:** DRAFT PR #342, HEAD `247a0247d8a3740d0c8483146be1740354d80c40`. **Status:** testprototyp, produktionsstatus **NO-GO**.

## Pass 1: verklig hotmodell

Efter #340 finns en SQLite-kandidat för verifierarnycklar, återkallelser och generationsbyte. Efter #342 finns en separat SQLite-kandidat som kan förbruka ett signerat operatörsnonce atomiskt. En gammal filkopia kan fortfarande acceptera samma nonce igen om angriparen också återställer hela databasen eller tillhörande kontrollpunkt. Det går **inte** att ge en allmän anti-rollback-garanti genom att bara signera en gammal, oföränderlig fil eller använda SQLite:s vanliga transaktionsgarantier.

En korrekt modell behöver minst:
- en oberoende, redan pinnad **vittnespublik nyckel**; den privata vittnesnyckeln får inte finnas hos runtime, CI, updater eller verifieraren;
- ett **separat betrott huvudankare** med den absolut senaste godkända checkpoint-hashen och initial geneshash;
- en monoton sekvens som inte kan hoppa bakåt, tappa spärrade nycklar eller glömma förbrukade operatörsnonces;
- ett säkert och beständigt förfarande som faktiskt uppdaterar det separata huvudankaret före något framtida produktionsgodkännande.

## Pass 2: källkodsimplementation

`core/selfdev_signed_witness_checkpoint.py` innehåller **enbart läsande** verifiering av signerade externa checkpoints. Den skapar aldrig en signerare, skriver ingen diskfil och kan inte starta någon updater eller promotion. Alla checkpointmeddelanden har exakt schema, avgränsad längd, kanonisk JSON och en separat domän för Ed25519-signaturen.

Ett checkpointbevis binder enhetsidentitet, sekvens, verifierarnyckelns publika bytes, dess SHA-256, verifierarepoch, den **fullständiga sorterade listan** över pensionerade verifierarnycklar och förbrukade operatörsnonces, föregående checkpoint-hash och en tidsstämpel.

`inspect_witness_chain` tar en vittnespublik nyckel, en betrodd genesis-SHA256, en betrodd aktuell head-SHA256 och förväntat enhets-ID **som externa argument**. Efter signaturkontroll krävs:
- Genesis: sekvens 1, föregående hash 0, och hash som matchar separat pinnad geneshash.
- Varje senare checkpoint: sekvens exakt +1, rätt föregående hash och icke-backande tid.
- Utan ny verifierarepoch: exakt samma publika nyckel och spärrlista, men **nya** förbrukade nonces måste ha lagts till.
- Vid ny verifierarepoch: exakt +1; ny verifierarnyckel; exakt den föregående aktiva nyckeln läggs till spärrlistan, ingen gammal spärr får försvinna och tidigare förbrukade nonces får aldrig tappas.
- Slutlig checkpoint-hash måste matcha **separat betrodd senaste head-SHA256**. Ett äldre men giltigt signerat checkpoint avvisas alltså om huvudankaret är uppdaterat.

De sorterade listorna är avsiktligt begränsade till 256 värden och kontrollkedjan till 32 poster. Denna enkelhet är en **skalbarhetsbegränsning i prototypen**. Den behövs för att hindra stora opålitliga signeringsmeddelanden, och utökning kräver ett separat granskat kompakt ackumulator-/Merkle-register.

Returtypen `WitnessSnapshot` är fryst och har alltid `actual_external_witness_storage_verified=False`, `power_loss_or_restore_resistance_verified=False`, `external_head_advancement_performed=False`, `authorizes_mutation=False` och `production_deployment_authorized=False`.

### Positivt och negativt rollback-test

`tests/test_selfdev_signed_witness_checkpoint.py` signerar bara med tillfälliga testnycklar. Ett gammalt, giltigt signerat checkpoint får inte godkännas när betrott senaste huvud har gått framåt. Testet verifierar också det **motsatta**: ett felaktigt stillastående senaste huvudankare kan fortfarande göra en äldre kedja accepterad. Signaturen ensam garanterar alltså aldrig färskhet.

Regressionssviten provar dessutom förfalskad signatur, annan vittnesnyckel eller enhet, dubbel JSON, ändrade hashvärden, osorterade/duplicerade listor, gammal verifierarepoch, borttappad spärr eller nonce, oförklarad sekvensändring, fel nyckelretirement och överskridna gränser.

## Separat Linux-identitet och privat testlagring

`scripts/test_disposable_witness_file_boundary.py` kör bara när processen är Docker-root, `/.dockerenv` finns och ett explicit miljötestvillkor är satt. Den skapar ett **fiktivt vittneskonto genom UID-byte i en testprocess**, numeriskt UID 23005, med 0700 privat katalog och 0600 head-fil. Vittnet ersätter två syntetiska, **osignerade** innehållsrevisioner genom tempfil, `fsync` av fil, `os.replace` och `fsync` av katalog.

Tre andra faktiska Linux-UID (updater 23001, runtime 23002, CI 23003) provar var för sig att läsa, skriva, skapa och byta ut den privata head-filen och ska få `PermissionError`. Testfilen innehåller **ingen** verklig nyckel, riktiga SQLite-data eller påstådd produktionssignatur. Det är två skilda tester, inte en installerad integrerad tjänst.

`.github/workflows/disposable-witness-file-boundary.yml` kräver GitHub-hostad Ubuntu, exakt commit-SHA, nätverkslös `--read-only` Docker med pinnad image-digest, enbart en läsbar testskriptfil, begränsade privilegier, tids-/minnesgränser och inget självhostat VENTUNO-jobb. Källkodstester i `tests/test_disposable_witness_file_boundary_source.py` bevakar dessa gränser även på ARM64 utan UID-byte.

## Fortsatt NO-GO: varför detta ännu inte är produktionsskydd

1. **Ingen betrodd extern signerare eller aktuell head-registertjänst installeras.** Den skyddade testfilen i Docker är inte ett hårdvaruförankrat, icke-återställbart huvud. En UID med root/samma vittneskonto, eller en angripare som kan återställa både fil och huvud, kan fortfarande spela upp gammalt tillstånd. `fsync` bevisar inte eMMC-strömavbrottssäkerhet.
2. **Ingen global flerdatabastransaktion.** SQLite-registret för nyckelrotation (#340), operatörsnonce (#342) och en framtida extern huvudankare-tjänst uppdateras inte atomiskt tillsammans i denna PR. Vi måste specificera order, replay-safe återhämtning och fail-closed vid mellanliggande strömavbrott.
3. **Ingen riktig mänsklig operatörsautentisering** och ingen skyddad separat fysisk operatörsnyckel. PR #341 verifierar bara en separat Ed25519-signatur.
4. **Ingen verklig VENTUNO-migrering.** Kontoinställningar, GitHub runner group-policy och fem historiska workflow-exponeringar kvarstår. Fysisk CPU/GPU/NPU, ljud, USB, Bluetooth, systemd, eMMC och återställning måste fortfarande undersökas före release.
5. **Inget självutvecklingsgodkännande.** Alla nya moduler och tester kan inte installera eller mutera produktionskoden, ändra riktig signeringsnyckel eller kopplas till `SelfDevPromotionManager`.

**Acceptans:** exakt sista commit ska ge grön fullständig GitHub-hostad ARM64-källkodssvit samt separat disposable Docker-UID-test. DRAFT, ingen `main`-merge, ingen VENTUNO-driftåtgärd, fortsatt **NO-GO**.
