# MyAI – auto-revert vid promotionsfel: no-follow-kontroll av aktiv kod (2026-10-17)

**Bas:** DRAFT PR #304 `95431804e750f1d91b60b5ec77d24fd51e1c67b1`. Enbart källkodsrevision och source-only ARM64-testning. Ingen aktiv återställning, promotion, installation eller merge till main.

## Pass 1 – logisk granskning

Om `_promote_impl` redan skapat PREPARED-journalen och ett fel uppstår under atomisk kopiering, kontrolleras vilka aktiva källfiler som verkligen behöver återställas. Den gamla exceptionhanteringen använde `target.is_symlink()`, `os.path.lexists(target)` och därefter `_sha256(target)` som tre skilda pathname-uppslagningar. En lokal skribent som kan byta ett förälderalias efter första kontrollen kunde göra att hashningen läste från en annan fil eller felaktigt bedömde en aktiv fil som oförändrad. Sådan manipulation måste stoppas innan automatiska återställningsförsök.

## Pass 2 – kodändring och regressioner

- De upprepade pathname-kontrollerna ersätts med **en** `_hash_existing_regular_path(target)` som öppnar föräldrar med `O_DIRECTORY|O_NOFOLLOW`, slutfilen med `O_NOFOLLOW|O_NONBLOCK`, kräver vanlig fil med en enda hårdlänk och beräknar hash från pinnad filbeskrivare.
- Om den aktiva filen inte kan öppnas säkert, finns på oväntad plats eller har en hash utanför tidigare/kopierat tillstånd, **avbryts automatisk rollback** med det befintliga kravet på manuell återställning. En saknad fil får endast hoppas över om den var en helt ny fil utan ursprunglig aktiv version.
- Resten av journalsystemet och `_restore_from_backup(...expected_after=planned_hashes)` lämnas oförändrat. Den avsedda skillnaden gäller enbart kontrollen **innan** automatisk restore.
- Tre nya regressioner: förälderkatalog flyttas och blir extern symlänk efter sista target-kontrollen när andra filens promotion fallerar; slutfil ersätts med extern symlänk; redan uppdaterad ursprunglig kodfil tas bort före auto-revert och får inte tyst återskapas.
- Tidigare tester för fsync-fel efter rename, användarändring av första eller andra filen, korrekt återställning samt journalstate ska fortsätta passera.

## Begränsningar

- POSIX erbjuder inte en atomisk kombinerad hash/rename/unlink för en icke-samarbetande lokal skrivare. Det här fixar pathname-omdirigerade **läsningar** i själva undantagskontrollen men ersätter inte globala processlås, privat UID, backupens egna integritetskontroller eller releaseproveniens.
- Read-only recoveryinspektion, normal rollback, äldre migrationsfall, sessioninventering och vissa övriga pathname-operationer måste fortsatt bedömas för varje verkligt hot.
- Full manuell fil-för-fil-granskning av projektet och beroenden/licenser/SBOM, fysisk strömavbrottsrecovery och NPU/ljud på VENTUNO återstår. Allt är DRAFT/NO-GO för main och installerad drift.

**Verifieringskrav:** full ARM64 source-only CI på exakt slutlig HEAD.
