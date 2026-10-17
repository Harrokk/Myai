# MyAI – legacy-journalens aktiva källkodsverifiering (2026-10-17)

**Bas:** grön DRAFT PR #301, commit `7d0e6978592787cf0d43775d6f385320849239f9`. Enbart källkod och ARM64 source-only-testning, ingen aktiv migrering eller annan filändring på VENTUNO.

## Pass 1: logik och verifiering

`SelfDevPromotionManager._migrate_legacy_completed_impl` är den manuellt auktoriserade migrationen av äldre osignerade, **slutförda** promotion-journaler. Journalen läses med strikt JSON och dess `after_hashes` jämförs med aktiv kod innan något arkiveras eller signeras. Den tidigare kodvägen använde `target.is_file()` och därefter `_sha256(target)`, vilket är två oberoende pathname-uppslagningar. En samtidiga skrivare kan byta en aktiv fil eller förälderkatalog till en symlänk mellan kontroll och hashning. Det kan förleda verifieringen eller åtminstone orsaka otillåten läsning från en annan fil.

## Pass 2: åtgärd och tester

- Varje tillåten källkodssökväg kontrolleras genom den befintliga `_safe_project_target`, och bytes SHA-256 beräknas genom `_hash_existing_regular_path(target)`. Den öppnar föräldrar med `O_DIRECTORY|O_NOFOLLOW`, sista filen med `O_NOFOLLOW|O_NONBLOCK`, avvisar specialfiler/hårdlänkar via `fstat`, och använder pinnad filbeskrivare.
- `OSError`, `PermissionError` och andra kontrollerade hashfel normaliseras till det existerande fail-closed-felet `Aktiv kod skiljer sig från legacy-journalen.` Ingen journal arkiveras eller signeras om källkoden inte kan verifieras.
- Fyra regressionstester: förälderkatalog byts till extern symlänk **efter** målpreflight; slutfil byts till extern symlänk efter kontroll; hårdlänkad aktiv fil avvisas; ändrad aktiv inode under hashning avvisas. Även tidigare testsuiter för normal migrering och upprepade migrationsförsök ska vara gröna.

## Fortfarande NO-GO

- Den separata `promotion.legacy-unsigned.json`-arkivfilen skapas och verifieras ännu med pathname-baserad `os.open`, `Path.read_bytes` och `_sync_directory(root)`. Den måste härdas separat; denna PR ändrar bara **aktiv källkodsverifiering**.
- HMAC-migration kan inte ersätta oberoende signerad releaseproveniens eller förhindra lokala privilegierade samtidiga writers efter sista hashkontrollen.
- Komplett manuell projektrevision, hårdvarufel/strömavbrott, beroende-/SBOM/licensrevision och fysisk VENTUNO/NPU/ljud-validering återstår.
- Ingen merge till main, ingen live promotion, rollback, återställning eller legacy-migration. Håll PR som DRAFT tills alla releasegrindar är klara.

**Verifiering:** full ARM64 source-only svit på exakt slutlig HEAD.
