# MyAI – inventering av avbrutna selfdev-uppdateringar (2026-10-17)

**Bas:** grön DRAFT PR #296 (`51538655f346413efab00fbf1bf7c163712dfae4`). Endast källkodsändringar och ARM64 source-only verifiering. Ingen aktiv promotion, rollback, installation eller merge till main.

## Pass 1: logik och dataflöde

`SelfDevPromotionManager._require_no_interrupted_promotion` är en viktig spärr som förhindrar att en ny selfdev-promotion påbörjas om **någon** känd session har en oavslutad journal. Före ändringen använde funktionen upprepade `Path.exists/is_symlink/is_dir/iterdir/is_file` och öppnade slutligen `promotion.json` på nytt via pathname i `_read_journal`. En lokal skribent som kan byta ett katalogalias mellan kontroll och `iterdir` eller mellan `iterdir` och journalöppning kan omdirigera inventeringen till en annan katalog och få en faktisk `prepared`-journal att förbises. En fil med giltig HMAC från annan plats skulle då kunna vilseleda inventeringens status utan att HMAC är bruten.

## Pass 2: säkerhet och åtgärd

- Varje sessionrot, sessionskatalog och promotionkatalog öppnas genom `_pinned_parent` och relativa `os.open(...,O_DIRECTORY|O_NOFOLLOW,dir_fd=...)`-anrop. Namn listas med `os.scandir(dir_fd)` medan själva katalogens filbeskrivare förblir öppen. Symlänkar avvisas och saknade journaler blockerar.
- Journalfilen öppnas `O_NOFOLLOW|O_NONBLOCK` relativt öppnad promotionkatalog, kontrolleras med `fstat` (vanlig fil, en hårdlänk, högst 1 MiB) och läses exakt en gång. Inodens storlek, dev/ino, mtime och ctime måste vara stabila under läsningen.
- Den befintliga **strikta JSON-parsern** är återanvändbar på redan lästa bytes, utan ändrade JSON-regler (unika nycklar, inga NaN/Infinity, begränsad storlek). `_read_journal` återanvänder en ny metod för samma HMAC-validering som gäller journalen från inventeringen.
- En explicit gräns på 10 000 katalogposter förhindrar obegränsad inventering. Saknade valfria sessionrötter hoppas över, medan symlänkad eller osäker katalog avvisas.
- Fem syntetiska regressioner: aliasbyte *efter* öppning av riktig journal, symlänksbyte av rollbackkatalog *före* öppning, symlänk i journalfil, borttagen journal och överstor journal. Befintliga tester av verkliga avbrutna promotion/rollback-fall ingår i helsviten.

## Kvarstående risker och NO-GO

- En privilegierad/icke-samarbetande process med skrivrätt till sessionernas föräldrar kan fortfarande byta namn eller skapa nya sessioner efter den slutliga inventeringen. Den globala selfdev-flocken omfattar bara samarbetsvilliga skribenter. Full garanti kräver process-UID och privata rootbehörigheter.
- Inventeringen är read-only på kod och journaler men HMAC-nyckeln hämtas separat under kontrollerade katalogbeskrivare.
- `inspect_recovery_artifacts` använder fortfarande pathname-baserad `os.scandir` och kräver egen säkerhetshärdning. Inventering av nya sessioner under pågående skanning är inte en atomisk global snapshot.
- Fysisk strömavbrottsåterställning, repo-wide filrevision, SBOM, beroenden, licenser, firmware, nativ ABI och NPU/ljudtest på VENTUNO kvarstår.
- Allt ligger i DRAFT, utan merge till main, utan ändring på `/home/arduino/MyAI` och utan aktiv självmodifiering.

**Verifieringskrav:** komplett ARM64 source-only CI på exakt slutlig PR-SHA. Vid fel räknas inte PR:n som godkänd.
