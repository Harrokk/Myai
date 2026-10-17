# MyAI – skrivskyddad recovery-preflight med verifierad aktiv filinode (2026-10-17)

**Bas:** godkänd DRAFT PR #298, SHA `e247dd33ad409dc91bc36ef75dce4ff0eb7157b6`, 3400 pass och 15 skip i full VENTUNO ARM64 source-only CI. Ny gren: `dev/manual-audit-selfdev-inspect-active-hash-dirfd-20261017`.

## Manuell granskning, pass 1: dataflöde

`SelfDevPromotionManager.inspect_recovery` ska enbart presentera en lägesbild av om återställning skulle vara möjlig. Funktionen validerar signerad journal, tillåtna filnamn, backup-hashar och aktuella projektfiler, men använde `target.is_file()`, `os.path.lexists(target)` och `_sha256(target)`. Den sista operationen gjorde ett nytt pathname-baserat `Path.open` efter att `_safe_project_target` hade kontrollerat symlänkar. En lokal filsystemsskribent kunde byta en förälderkatalog mellan dessa anrop och omdirigera läsningen till externa filer. Särskilt farligt för en **read-only** statusfråga som inte behöver läsa någon annan data än verifierad projektkod.

## Pass 2: avgränsad åtgärd och verifieringskrav

- Alla aktiva fildigester i `inspect_recovery`, både ändrade befintliga filer och tillagda filer, beräknas nu via befintliga `_hash_existing_regular_path(target)`. Den öppnar varje förälderkatalog genom `_pinned_parent` med `O_DIRECTORY|O_NOFOLLOW`, öppnar sista filkomponenten relativt FD med `O_NOFOLLOW|O_NONBLOCK`, kräver vanlig fil med exakt en hårdlänk och beräknar hashen från samma låsta FD.
- Befintlig fil som försvunnit eller inte kan öppnas orsakar `blocked`; ny fil som aldrig skapats är fortfarande tillåten (behöver ingen radering), men existerande felaktig/symlinkad/hårdlänkad ny fil blockeras.
- Samma existerande journal- och backup-HMAC-proveniens och statusformat bevaras. Ingen data skrivs, ingen auditlogg eller OS-lock öppnas genom denna statusfråga.
- Tre syntetiska tester: bytt förälderkatalog *efter* target-validering, tillagd målfil bytt till extern symlänk efter kontroll, och hårdlänkad aktiv fil avvisas.
- Befintliga unit- och systemregressioner för `inspect_recovery` och faktiskt manuellt `recover_interrupted` körs tillsammans i full ARM64-svit.

## Kvarvarande osäkerhet / NO-GO

- `_recover_interrupted_impl` och delar av normal `rollback` använder fortfarande pathname-baserad `target.is_file`/hashkontroll; detta kräver egen ändring. Den här PR:n härdar **enbart read-only förhandsgranskning**, inte själva återställningen.
- En lokal osamarbetsvillig writer kan manipulera samma öppna filinode under hashning; den befintliga pinned hash-helpern jämför metadata men full skyddsgaranti kräver OS-/UID-isolering. Den här statusinformationen får aldrig användas för att kringgå explicit återställningsfras.
- Fullständig projekt- och beroenderevision, DNS/SSRF, SBOM/licenser/nativa bibliotek, fysisk NPU-/röstverifiering och riktig strömavbrottsåterställning återstår.
- Ingen merge/deployment eller aktiv selfdev-promotion/rollback på VENTUNO; PR:n förblir DRAFT.

**CI-gate:** kör hela source-only ARM64-sviten på exakt HEAD och redovisa fel/skips, inte enbart tidigare commit.
