# MyAI: återhämtningsgranskning efter avbrutna SQLite-/vittnesuppdateringar

**Datum:** 2026-10-18. **Bas:** DRAFT PR #343, HEAD `06674ab318ae1d6530c33d9bdcccc9e44e749980`.

**Status: offline granskningsmodell, ingen produktionsåterställning. ALLTID NO-GO.**

## Första passet – felmodellen

PR #340 innehåller ett SQLite-*kandidatregister* för verifieringsnycklar och återkallelser, PR #342 ett separat SQLite-*kandidatregister* för operatörens engångsutmaningar och PR #343 kryptografisk granskning av ett externt signerat kontrollbevis samt ett Docker-only UID-lagringstest. De tre består av **separata transaktionsdomäner**: en SQLite-transaktion kan inte garantera atomisk commit med en oberoende signeringstjänst eller ett separat, långsiktigt pinnat vittneshuvud.

Ett strömavbrott eller en processkrasch kan därför inträffa när *endast ett delsystem* registrerat en förbrukad nonce eller nyckelgeneration. Att på egen hand köra om de saknade skrivningarna är farligt: det kan godkänna en gammal operatörssignatur, ta bort en återkallelse eller acceptera en falsk vittneskedja.

**Säker grundregel:** Om det signerade vittneshuvudet, nyckelregistret och förbrukade operatörsnonces inte överensstämmer ska systemet **stoppa** och begära separat kontrollerad manuell incidentbedömning. Även full överensstämmelse är **inte** i sig ett driftsgodkännande utan kräver bekräftad färskhet hos det fristående huvudankaret, exklusiv skrivarspärr, strömavbrottstester, nyckel-/operatörsprovisionering och auktoriserad policy.

## Andra passet – faktisk ändring

`core/selfdev_recovery_consistency.py` inför en ren **inspektionsfunktion** med två redan öppnade caller-owned SQLite-anslutningar plus PR #343:s signerade vittneskedja. Den skapar inga databaser, öppnar inga filer, ändrar ingen nyckel, signerar inga bevis och utför ingen automatisk reparation.

`inspect_recovery_consistency` kontrollerar först Ed25519-vittneskedjans signaturer mot en separat pinnad publik nyckel, dess genesis-SHA-256, **aktuell separat förväntad head-SHA-256** och förväntat enhets-ID. Sedan öppnar den endast **read transactions** med `BEGIN` på de två befintliga SQLite-anslutningarna, läser exakt en kandidatnyckel/epoch och den fullständiga återkallelselistan samt en bunden mängd operatorutmaningar med förbrukningsstatus. Båda read-transaktionerna stängs med `ROLLBACK` för att inte lämna lås eller modifiera data.

Det lästa jämförs fält för fält mot vittnesbeviset. Möjliga avvikelsekategorier:

| Avbrottspunkt | Typisk avvikelse | Automatiskt återupptagande |
|---|---|---|
| Ingen övergång; tre delar motsvarar samma signerade huvud | Inga lokala skillnader | **Nej** – bara kandidatöverensstämmelse |
| SQLite märkte nonce som förbrukad före nästa vittnesbevis | `candidate_consumptions_not_witnessed` | **Nej** |
| Vittnet avancerade nonce innan SQLite markerade förbrukad | `witnessed_consumptions_missing_from_candidate` | **Nej** |
| SQLite flyttade nyckelgeneration före vittnet | `candidate_key_epoch_ahead_of_witness` | **Nej** |
| Vittnet flyttade nyckelgeneration före SQLite | `candidate_key_epoch_behind_witness` | **Nej** |
| Aktuell nyckel, spärrlista eller signerad historik skiljer sig | Identitets-/spärrlisteskillnad eller **undantag** | **Nej** |
| Gammal SQLite-snapshot men nyare **betrott** vittneshuvud | Epoch/nonce/spärrlisteskillnad | **Nej** |
| Gammal SQLite-snapshot **och också rollbackat externt pinnat huvud** | Kan framstå som korrekt | **Nej** – ingen bevisad färskhet |

Returtypen `RecoveryInspection` innehåller observerade skillnader och markerar alltid `safe_to_resume_production=False`, `automatic_repair_permitted=False`, `authorizes_mutation=False`, `production_deployment_authorized=False`, `independent_live_head_freshness_verified=False`, `cross_database_atomic_snapshot_verified=False` och `external_durable_commit_verified=False`.

`tests/test_selfdev_recovery_consistency.py` skapar tillfälliga SQLite-kandidatdatabaser och tillfälliga Ed25519-vittnesnycklar. Den går igenom varje avbrottspunkt, signerar två påföljande förändringar (nonce-förbrukning och nyckelrotation), testar olika skrivningsordningar, manipulerade databaser, ogiltiga vittnesnycklar, avvikande enhets-ID, trasiga databastabeller, oväntade aktiva transaktioner och negativt scenario där ett gammalt betrott huvud inte upptäcker total rollback.

## Fortfarande väsentliga blockerare

1. **Ingen global tidsmässigt atomisk läsning:** de två SQLite-anslutningarnas lästransaktioner ger lokala snapshots, inte en transaktion som är atomisk med en extern vittnestjänst. Riktiga tjänster måste först spärra skrivare och använda betrodd sessions-/generationstilldelning innan en sådan läsning får påverka något beslut.
2. **Ingen riktig extern monotont skyddad huvudlagring:** PR #343:s Docker-fil demonstrerar UNIX-DAC och `fsync` på syntetisk data, inte strömavbrottssäker, anti-rollback-säker eMMC/TPM/RPMB. Full rollback tillsammans med den förankrade huvudhashen kan fortfarande gömma en incident.
3. **Ingen distribuerad tvåfas-/intentsjournal och ingen recovery-controller:** detta är en felsökningsmodell med **endast läsning**. Att reparera divergenta register eller återuppta signering/uppdateringar kräver ett separat konstruerat och granskat fail-closed-protokoll, inklusive osäkra och mellanliggande tillstånd.
4. **Ingen fysisk VENTUNO-verifiering:** Linux-UID/ACL, verkliga systemd-enheter, GitHub runner-grupp och historiska självhostade workflows, strömavbrott på eMMC, NPU, ljud och Bluetooth har inte testats eller ändrats.
5. **Ingen administrationsauktorisering eller promotion:** PR #341:s giltiga operator-Ed25519-signatur bevisar inte personlig autentisering. Detta är inte en installerad signeringstjänst eller en godkänd koduppdatering.

**DRAFT-acceptans:** alla källkodstester på exakt sista GitHub-hostade ARM64-commit måste vara gröna. Inga ändringar i `main`, inga fysiska runner-jobb eller VENTUNO-åtgärder. Produktionsstatus **NO-GO**.
