# MyAI – kandidatjournal för avbrutna nyckelbyten och fail-closed granskning

**Datum:** 2026-10-19. **Bas:** DRAFT PR #344, HEAD `70154e4c52ed01e2ad116765c5d1b61922bdb6f6`.

**Status: endast offline testmodell. Ingen produktion, ingen VENTUNO-åtkomst, NO-GO.**

## Första granskningspasset – varför en journal behövs

PR #344 upptäcker skillnader mellan två separata SQLite-kandidatregister (operatörens förbrukade godkännanden respektive verifierarens nyckelgeneration) och ett oberoende Ed25519-signerat vittneshuvud. Vid en krasch kan en eller flera av dessa uppdateras utan att de andra hunnit göra det. Ett framtida återhämtningsförfarande behöver en identifierbar *avsikt*, förväntade generationer/nonce/hashar och en historik över lokalt observerade etapper.

Ett lokalt journalsteg kan dock **inte** ensamt bevisa att en extern vittnestjänst utfört något. En hashkedja inom samma SQLite-fil ger inte kryptografiskt skydd mot en angripare som kan räkna om alla hashvärden eller återställa en äldre journal och huvudankare.

## Andra granskningspasset – levererad kod

`core/selfdev_candidate_crash_intent_journal.py` skapar två separat namngivna tabeller **bara på en redan öppnad SQLite-anslutning som anroparen äger**. Ingen annan SQLite-fil, updater, fysisk enhet, signeringsnyckel eller systemd-tjänst öppnas.

En planerad kandidatavsikt måste ha: strikt identifierad intent, enhets-ID, unikt 128-bitars operatörsnonce, verifierarnyckelgeneration old → old+1, SHA-256 för förväntat rotationsförslag, och två **från separat betrodd planering förväntade** men ännu *inte autentiserade* vittneshuvudhashar.

Journalens tillåtna lokalregistrerade stadier är exakt:

| Etapp | Betydelse som lokal journalanteckning | Produktionsåterupptagande |
|---|---|---|
| `prepared` | Avsikt registrerad; ingen extern åtgärd bevisad | **Förbjudet** |
| `operator_db_recorded` | Påstådd lokal nonce-förbrukning | **Förbjudet** |
| `operator_witness_recorded` | Påstådd signerat vittneshuvud efter nonce-förbrukning | **Förbjudet** |
| `key_db_recorded` | Påstådd lokal kandidatnyckelrotation | **Förbjudet** |
| `key_witness_recorded` | Påstådd slutlig vittnesrotation | **Förbjudet** |

Ordningen är strikt. Varje steg är en **separat kandidat-SQLite-transaktion** med `BEGIN IMMEDIATE`, CAS-liknande kontroll av föregående steg, primärnycklar för att neka dubletter och SHA-256 över avsikt, steg, föregående steg-hash och observerad *påstådd* witness-head. Journalen kan inte hoppa över, dubblera, bakdatera eller byta huvudhash utan att koden stoppar. Det sista steget registreras men ger aldrig rätt att aktivera ny nyckel.

`inspect_candidate_intent_recovery` kombinerar en granskad lokal journal med en `RecoveryInspection` från PR #344. Det jämför enhets-ID, planerad verifierarepoch och motstridiga vittneshuvudpåståenden. Avvikelser listas för vidare kontroll; **även noll avvikelser** ger alltid `manual_reconciliation_required=True`, `automatic_resume_permitted=False`, `external_head_freshness_verified=False`, `journal_stage_is_externally_proven=False`, `authorizes_mutation=False`, `production_deployment_authorized=False`. Ett anroparskapat Python-objekt är inte en signerad oberoende säkerhetsauktoritet.

`tests/test_selfdev_candidate_crash_intent_journal.py` använder **tre tillfälliga SQLite-filer**, temporära Ed25519-vittnesnycklar, riktig signerad vittneskedja och PR #344:s faktiska `inspect_recovery_consistency`. Följande felscenarier och attackfall provas:

- All fem journaletapper, SQLite-omstart och ordningsbrott/skippade/förfalskade steg.
- Två samtidiga anslutningar som försöker skriva samma nästa steg – bara en får lyckas.
- Ändring av sparat steg, tidigare hash, slutlig hash, nonce, enhet och verifierarepoch.
- Avbrott direkt efter `operator_db_recorded` men före oberoende vittne, och motsvarande händelse när viktiga loggar divergerar.
- Nyckelrotation efter lokal commit men före slutligt vittneshuvud.
- Tre delar kan stämma när journalen är på sista steget, men det är ändå **inte** ett produktionsgodkännande.
- Återställning av ett gammalt journalhuvud tillsammans med en gammal extern huvudhash demonstrerar ett oupptäckt lokalt rollbackfall; modellen får därför aldrig hävda fysisk anti-rollback.

## Öppet inför riktig installation

1. **Verifierad händelseproveniens:** ingen tjänst kan ännu kryptografiskt bevisa att ett journalsteg följts av en riktig operatörs- eller vittnestransaktion. En anroparstyrd hash duger inte.
2. **Distribuerad hållbar commit saknas:** ingen atomisk uppdatering över olika SQLite-filer + extern vittnestjänst; ingen root-skyddad, beständigt pinnad monotont huvudlagring och ingen efterkraschåterhämtning med ombudshandläggning.
3. **Ingen produktionslåsning:** logik för att exklusivt pausa runtime/verifierare/updater under inspektionen saknas. Enhetens faktiska Unix UID/ACL och GitHub runner-grupp kvarstår.
4. **Ingen VENTUNO-hårdvarukontroll:** eMMC vid strömavbrott, ljud, USB, Bluetooth, NPU, systemd samt verkliga verifierarnycklar/administratörsgodkännande måste prövas separat.
5. **Ingen automatisk promotion:** koden öppnar inga fysiska enheter, flyttar inga nycklar eller startar inga självutvecklingsfunktioner.

**Acceptans:** exakt sista GitHub-hostade ARM64-kodsvit måste godkännas. DRAFT / NO-GO. Ingen merge till main eller ändring på fysisk VENTUNO.
