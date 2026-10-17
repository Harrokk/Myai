# MyAI – granskning av aktiva kodmålsökvägar (2026-10-17)

**Bas:** DRAFT PR #290 exakt SHA `0af56954c248313d29ff5d8759209d5e22148bc9`. **Ny gren:** `dev/manual-audit-selfdev-project-target-dirfd-20261017`. Endast källkod i GitHub och ARM64 source-only CI, ingen aktiv installation.

## Pass 1 – kontrollflöde

`SelfDevPromotionManager._safe_project_target(relative)` används före promotion, rollback och manuell recovery, inklusive när journalmetadata anger en kodfil. Gamla funktionen använde `target.resolve(strict=False)`, `root.resolve()` och flera separata `is_symlink()`-kontroller på föräldrar och slutfil. Alla kontroller gjorde nya sökvägsuppslagningar. En lokal process med rätt att byta förälderkatalog kunde ompeka efter kontroll och före nästa uppslagning. Kodsäkra `_atomic_copy` hade redan no-follow-förankring, men förhandskontrollen gjorde inte samma sak.

## Pass 2 – ändring och kontrakt

- Behåller kodens tillåtna sökvägspolicy och returnerar samma `Path`-värde till befintliga callers.
- Förankrar den betrodda projektroten med `_pinned_parent(root / ".selfdev-root-check")`. Går sedan varje **befintligt** mellanliggande katalogled med `os.open(..., O_DIRECTORY|O_NOFOLLOW, dir_fd=...)`.
- En befintlig symlänk i en förälderkatalog ger fail-closed `PermissionError`; en saknad förälderkatalog accepteras, eftersom godkända nytillkomna kodfiler får placeras i ännu inte skapade `tests/`- och andra tillåtna underkataloger.
- Om målfilens föräldrar finns kontrolleras slutnamnet med `os.stat(...follow_symlinks=False,dir_fd=...)`. En befintlig slutfil måste vara vanlig fil; symlänk, FIFO och annan specialfil avvisas utan att öppnas.
- Säkra `_atomic_copy` och `_unlink_verified_added` fortsätter att förankra och kontrollera filsystemet på nytt vid faktisk mutation: denna preflight är aldrig ensam tillräcklig säkerhetsgräns.
- Fem syntetiska regressionstester: befintlig föräldersymlänk, förälderkatalog byts efter förhandsberäkning men före `os.open`, slutfilssymlänk, tillåten saknad målkatalog, samt FIFO i målfilen.

## Kvarvarande risker – NO-GO

- Denna förändring tar bort pathname-baserad `resolve()` ur **just aktiv kodmålsförhandskontroll**. Övriga sökvägsberoende kontroller i `_safe_backup_path`, `_require_no_interrupted_promotion`, recovery-/journalmetadata och cleanup behöver fortsatt granskning.
- POSIX pathname/rename är inte atomisk compare-and-swap mellan oberoende writers; en lokalt privilegierad angripare med skrivrätt i katalogen kan fortfarande påverka namn i smala racefönster trots dirfd-kontroll. Separat UID/behörighetsmodell krävs.
- Full fysisk recovery vid strömavbrott, beroende-/licens-SBOM, native ABI och VENTUNO NPU/rösttest är ännu inte genomförda. Det återstår också en komplett manuell repositoryrevision fil-för-fil.
- **DRAFT och NO-GO för merge/deploy/aktiv promotion/recovery.** Kräv helt grön ARM64-testsvit på exakt HEAD.


**Testkorrigering:** Gemensam testfixture skapar normalt `tests/`; testet för en legitim saknad målkatalog raderar därför först endast den tillfälliga testkopian av `tests/`, innan `_safe_project_target` anropas. Första ARM64-körningen föll enbart på det tidigare felaktiga fixture-antagandet (1 failed, 3 370 passed). Den faktiska säkerhetsändringen har inte behövt backas ut.
