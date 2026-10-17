# MyAI – återställningsjournal: atomär, dirfd-förankrad publicering (2026-10-17)

**Bas:** DRAFT PR #282 commit `1bd71d5adffa59480136690d10972380e57876a6`. **Gren:** `dev/manual-audit-selfdev-journal-atomic-dirfd-20261017`. Källa och offline-tester endast, aldrig aktiva selfdev- eller rollback-operationer.

## Pass 1: logik och flödeskrav

`_atomic_write_record(path, record)` publicerar återställningsjournalen innan aktiv källkod ersätts, samt uppdaterar journalen vid komplett promotion/rollback eller efter ett avbrott. Tidigare skrev den via `tempfile.mkstemp(dir=path.parent)`, `os.replace(temp, path)` och `os.open(path.parent, O_DIRECTORY)`. Byten av en förälderkatalog efter initial kontroll kunde leda journalen utanför avsett sessions-/rollback-träd. Tidigare avvisades inte heller existerande symlänk/hårdlänkad journal innan ett nytt record skrevs. Läsaren hade redan en 1-MiB-gräns, men skrivaren hade ingen motsvarande.

## Pass 2: åtgärd och säkerhet

- Skrivaren serialiserar hela journalen med `json.dumps(... allow_nan=False)`, UTF-8, och avvisar JSON som överskrider 1 MiB **innan någon filsystemändring**.
- `_pinned_parent(path, create=True)` öppnar varje katalogled med `O_DIRECTORY|O_NOFOLLOW`. Existerande journalkandidat kontrolleras via `os.stat(...follow_symlinks=False,dir_fd=...)`; endast en vanlig fil med en länk är acceptabel.
- Temporär journal skapas exklusivt som slumpat namn `O_CREAT|O_EXCL|O_NOFOLLOW` (0o600), bytes synkas till disk via `fsync`, och `os.replace` publicerar från/så samma öppna katalog-fd. Parentkatalog-fd synkas efter rename. Vid fel tas endast den temporära filen bort, också via `dir_fd`.
- Före rename kontrolleras att befintligt journalnamn fortfarande motsvarar samma tillåtna reguljära inode, eller förblir frånvarande när det var frånvarande vid början.
- Fem syntetiska tester: länkad journal avvisas, journal med flera hårdlänkar avvisas, symlänksbyte av förälderalias mitt under rename kan inte omdirigera journalen, rename-fel lämnar tidigare journal orörd och städar temporära namn, överskriven storleksgräns ger inget katalogskapande.

## Fortsatta NO-GO-punkter

- Den sista jämförelsen mellan befintlig inode och `os.replace` är inte atomär gentemot en lokal icke-samarbetande writer; en sådan kan ändra eller byta **samma** journalnamn i det smala tidsfönstret. Journalens HMAC och projektlås är separata spärrar, men full säkerhet kräver skyddad UID-/katalogägarmodell.
- `_read_recovery_json`, `_journal_integrity_key` och `_verified_backup/_backup_verified_snapshot` använder på andra platser fortfarande pathname-baserad I/O för vissa katalogkomponenter. Dessa är ännu inte stängda i denna PR.
- Fristående makt att starta promotion/recovery är inte tillförd; all mutation förblir manuell och låst. Ingen fysisk power-loss/rollbacktest är utförd.
- Fullständig fil-för-fil-kodrevision, komplett nativ SBOM/licenser och fysisk VENTUNO NPU/ljud/firmware återstår. **DRAFT/NO-GO för main/produktion.**

**Verifieringskrav:** grön exakt-HEAD ARM64 source-only CI med full projekt- och säkerhetstestsvit före signoff.
