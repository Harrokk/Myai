# MyAI – normal rollback: pinnad validering av aktiv källkod (2026-10-17)

**Bas:** DRAFT PR #305 `42116f7252e56aad51b6ae33bd31c9149de97ff2`. Endast DRAFT-källkod och source-only ARM64-testning, ingen verklig rollback eller VENTUNO-installationsändring.

## Pass 1 – granskat flöde och säkerhetsfynd

Före att vanlig `ROLLBACK session_id promotion_id` får starta, läser `_rollback_impl` den signerade journalens `after_hashes` och jämför varje aktiv fil med den version som tidigare promoverats. Den tidigare sekvensen använde `not target.exists()` och `_sha256(target)`, två separata pathname-uppslagningar. En samtidig förälderkatalog- eller slutfilssymlänk efter `exists()` kunde dirigera hashningen utanför aktiv projektrot. Att senare `_atomic_copy` kräver pinnade inoder skyddade ersättningen, men inte denna preflightläsning.

## Pass 2 – åtgärd och verifiering

- Hashberäkningen sker nu via `_hash_existing_regular_path(target)`, som öppnar varje förälder med `O_DIRECTORY|O_NOFOLLOW` och sista filen `O_NOFOLLOW|O_NONBLOCK`, kräver vanlig fil med exakt en hårdlänk och beräknar hash från redan öppnad inode.
- Oväntad symlänk, saknad fil, hårdlänk, annan I/O-/integritetsavvikelse eller fel hash blir samma kontrollerade blockerande fel som tidigare: `Aktiv källkod har ändrats efter promotion`. Det sker **innan** signerat journalstate övergår till `rollback_prepared` eller aktiv kod ändras.
- Fyra syntetiska regressionstester: förälderkatalogalias byts till extern symlänk efter sista target-kontroll; aktiv slutfil byts till extern symlänk; ny hårdlänk skapas till aktiv kod; tidigare promoverad fil saknas. Tidigare tester av normal lyckad rollback, backupinoder, avbrott och manuell recovery ingår i full ARM64-suite.

## Risker som återstår (NO-GO)

- Detta är en pinnad hash-observation, inte ett atomärt transaktionslås mot lokal process med skrivrätt. Global flock gäller samarbetsvilliga sessioner och privat UID-/filägarskapsmodell måste fortfarande kontrolleras före fysisk deployment.
- Signerad journal kan inte ersätta separat signerad releaseproveniens; osignerade gamla journaler kräver explicit auktoriserad migration.
- Fullständig projektrevision fil-för-fil, beroenden/SBOM/licenser/ABI och VENTUNO:s fysiska strömavbrotts-/NPU-/ljudtester återstår. Ingen merge till main eller aktiv selfdev-operation. Alla ändringar DRAFT tills releasegrindarna är gröna.

**Verifieringskrav:** full source-only ARM64 CI på exakt sista commit.
