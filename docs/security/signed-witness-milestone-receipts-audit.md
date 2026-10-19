# MyAI – separat Ed25519-signerat vittneskvitto knutet till kraschjournalen

**Datum: 2026-10-19. Bas: DRAFT PR #345, HEAD `6d35455e5e09b26a16d48aa7d541ae56b0cd1b16`. Status: källkodskontroll, DRAFT, NO-GO.**

## Granskningspass 1 – kvarstående proveniensbrist

PR #343 kontrollerade riktiga Ed25519-signaturer över en extern vittneskedja och lokal Unix-DAC i en disposable Docker-miljö. PR #344 jämförde kandidatregister för verifierarnycklar och konsumerade operatörsnonces mot vittneshuvudet. PR #345 byggde en separat kandidatjournal med kontrollsummekedja för fem stadier.

Den journalen är **inte autentiserad händelseproveniens**. Ett påstående om att en lokal databas uppdaterats eller att ett vittne avancerat är bara en post i en annan SQLite-fil; en angripare som kan skriva denna fil kan räkna om SHA-256-kedjan. Inte heller ett gammalt men giltigt signerat vittneshuvud bevisar färskhet om det senast pinnade huvudankaret också är gammalt.

## Granskningspass 2 – levererad kontroll

`core/selfdev_signed_witness_milestone.py` introducerar en **ren inspektionsmodul**, inte en signeringstjänst. Ett strikt, domänseparerat och Ed25519-signerat kvitto binder:

- förväntat enhets-ID, exakt journalavsikt och journalens **aktuella händelse-SHA256**;
- exakt rotations-SHA256, 128-bitars operatörsnonce och gammal/ny verifierarepoch;
- verklig kontrollerad vittnessekvens, vittneshuvudets signerade digest och giltighet på högst 120 sekunder;
- mottagare och syfte som uteslutande avser **offline-inspektion**.

Signaturen måste kunna verifieras med en **separat, utifrån betrott fastställd Ed25519-kvittonyckel**. Samma offentliga nyckel får inte användas för kvitton och vittneskontroll. Den signerade vittneskedjan valideras **oberoende** med PR #343 mot extern, pinnad genesis-SHA256 och ett *separat förväntat senaste huvud*. Därefter kontrolleras journalens faktiska lästa innehåll under en SQLite-lästransaktion: enhet, avsikt, nonce, rotation, generation, händelsedigest, exakt väntat vittneshuvud och giltig ordning måste stämma.

**Avsiktlig begränsning:** bara journalstegen `operator_witness_recorded` och `key_witness_recorded` stöds. För det första krävs verifierarepoch oförändrad, att operatörsnonce förekommer i det signerade huvudet och att huvudet är journalens väntade mellanläge. För det andra krävs nästa verifierarepoch, att operatörsnonce inte tappats och att det signerade vittnet pensionerat föregående aktiva verifierarnyckel. Rena databassteg `operator_db_recorded` och `key_db_recorded` kan **inte** ges ett falskt ”vittnesbevis” med denna funktion.

Den nya returtypen `MilestoneReceiptInspection` förblir fryst med **ständigt falska** `receipt_signer_independent_execution_proven`, `real_external_write_observed`, `external_head_freshness_verified`, `operator_human_intent_verified`, `automatic_recovery_permitted`, `authorizes_mutation` och `production_deployment_authorized`. De första fyra fälten är inte säkerställda förrän en verkligt isolerad tjänst med säker nyckelhantering utför händelsen och producerar kvittot utan att förlita sig på runtime-kontrollerad JSON. Att verifiera en signatur bevisar innehav av nyckeln, **inte** att den signerande parten observerat en verklig disktransaktion.

`tests/test_selfdev_signed_witness_milestone.py` skapar test-Ed25519-nycklar och tillfälliga SQLite-journaler. Den testar båda vittnesstadierna, verifierar vittnets nonce/epoch/nyckelpensionering och kräver fel vid:

- förfalskad eller utbytt kvitto- eller vittnessignatur;
- identitets-, intent-, nonce-, journalhash- och rotationshashbyte;
- annan vittnessekvens, gammalt vittneshuvud eller för gammalt/framtida tidsfönster;
- dubbla JSON-nycklar, okända fält, avvikande syftesdomän eller för stort meddelande;
- att journalen fortsätter ett steg efter att kvittot signerats;
- återanvändning av samma publika nyckel mellan kvitto och vittne;
- osignerade journalsteg som försöker få status som externt verifierade.

## Kvarstående blockerare

1. **Ingen oberoende levande kvittoutställare finns.** En runtime kan ännu inte få ett autentiskt kvitto från en instans med annan UID, egna skyddade signeringsnycklar, faktisk händelseobservation och installationssäker IPC. Den nya modulen signerarar inte, skriver ingenting och installerar inga tjänster.
2. **Ingen bevisad extern senaste-head-provisionering eller anti-rollback.** Ett gammalt signerat vittneshuvud plus ett lika gammalt externt förväntat huvud kan fortfarande ge godkänd *historisk* inspektion. Alla fält som skulle indikera färskhet/återställningsrätt förblir false.
3. **Ingen bevisad SQLite-/vittnesatomaritet.** Detta jämför offline-värden; tre kandidatdatabaser och ett externt vittne är inte en atomisk transaktionsdomän. Lokal SHA-kedja och SQLite-kvitton ersätter inte en trygg tvåfas-/avstämningsarkitektur.
4. **Ingen riktig användarautentisering eller release.** Alla privata nycklar i testerna är syntetiska. PR #341:s godkända Ed25519-operatörssignatur bevisar inte faktisk mänsklig avsikt.
5. **Ingen fysisk VENTUNO-verifiering:** process-UID/ACL, GitHub-runnergrupper och äldre arbetsflöden, eMMC vid strömavbrott, QNN/NPU, ljud, USB, Bluetooth och systemd återstår.

**Acceptans för denna DRAFT:** fullständig GitHub-hostad ARM64-projektsvit på exakt sista HEAD, utan självhostad runner. Ingen `main`-merge, fysisk VENTUNO-åtgärd eller automatisk koduppdatering. Produktion: NO-GO.
