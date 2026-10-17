# MyAI – staging-källfiler: no-follow-hash före och efter PREPARED-journal (2026-10-17)

**Bas:** DRAFT PR #303, commit `fa3aa94b21d62a953b18f7a7aceab34f3baf77ed`. Endast källkod, GitHub source-only ARM64-tester, ingen aktiv promotion, rollback, migrering eller utrullning.

## Pass 1 – granskat kodflöde

`SelfDevPromotionManager._promote_impl` läste två gånger stagingkällfiler via `_sha256(source)`: dels **efter** att promotion-preflight godkänt manifestet och innan privata rollback-backuper skapades, dels **efter** PREPARED-journalen och före själva atomiska aktiva källkodsersättningen. Källfilens hash jämfördes mot stagingmanifestet, men `_sha256` öppnade sökvägen med vanlig `Path.open`. En samtidig symlänksväxling av slutfil eller förälderkatalog kunde därför få båda verifieringarna att läsa en annan, eventuellt extern fil. Att den senare `_atomic_copy` redan avvisar symlänkar skyddade själva ersättningen men inte de tidigare otillåtna läsningarna.

## Pass 2 – åtgärd

- Båda anropen ersätts med den befintliga `_hash_existing_regular_path(source)`. Den använder `_pinned_parent` med `O_DIRECTORY|O_NOFOLLOW` i varje katalogled, öppnar slutfilen med `O_NOFOLLOW|O_NONBLOCK`, kontrollerar vanlig fil med en enda hårdlänk och beräknar SHA-256 från den pinnade filbeskrivaren under samtidighetskontroll.
- Manifestdigest, ordning kring PREPARED, godkännandefras, tidigare backupkontroller och `_atomic_copy(...expected_old,expected_source)` ändras inte.
- Fyra nya offline-regressioner: stagingfil byts till extern symlänk efter preflight; stagingförälder byts efter preflight; filen byts efter PREPARED-journal men före promotionkopiering; stagingfil får oväntad extra hårdlänk efter preflight.
- Vid upptäckt före PREPARED städas endast ofärdiga backuper enligt redan härdad logik. Efter PREPARED ska den signerade journalen övergå till det befintliga, kontrollerade `reverted`-flödet utan att någon aktiv fil skrivs över.

## Fortsatt NO-GO

- Aktiv filkontroll via `target.exists()` före backup, läsning av slutlig målkod under exception-baserad auto-revert och vissa äldre migrerings-/inventeringsvägar är ännu inte samtliga atomiskt härdade mot en lokalt privilegierad icke-samarbetande process.
- En positiv filhash är en observation av en viss inode, inte ett lås för framtiden. OS-behörigheter och global samarbetslåsning krävs för att förhindra nya filbyten mellan separata steg.
- Fullständig manuell repo-/beroende-/SBOM-revision, fysisk VENTUNO/NPU/ljud-validering och verkliga avbrottstester återstår. Alla PR:er förblir DRAFT utan main-merge och utan ändring i installerad MyAI.

**Verifieringsgrind:** full ARM64 source-only CI på exakt slutlig HEAD.
