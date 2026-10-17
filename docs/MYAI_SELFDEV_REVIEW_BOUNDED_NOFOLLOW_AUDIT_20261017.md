# MyAI — selfdev review: filåtkomst, diff och resurser (2026-10-17)

**Bas:** godkänd DRAFT PR #280, commit `0a7db0e55c6dd0858c04c824d1987c57384ce681`. **Gren:** `dev/manual-audit-selfdev-review-bounded-nofollow-20261017`. Endast GitHub-källkod och offline/isoleringstester, ingen aktiv MyAI-installation.

## Pass 1: kod- och flödesgranskning

`core/selfdev_review.py` läste både aktiv projektfil och stagingfil med `path.exists()` och `path.read_text()`, konstruerade en full `difflib.unified_diff` och avkortade först efter att alla resultat satts ihop. Trots `max_diff_chars` kunde därför en stor eller fientlig fil laddas helt i minnet och göra granskningen dyr. `exists`/öppna-anropen utgjorde två skilda uppslagningar och kunde följa en utbytt symlänk.

Granskningen ska fortsatt visa ändrade/tillagda/raderade sökvägar, exakt diff vid rimlig storlek och markera `diff_truncated` när outputgränsen nås. Förväntat saknad aktiv fil vid en add eller saknad stagingfil vid en delete ska tolereras; en ändrad fil som försvinner däremellan får **inte** tyst jämföras som tom.

## Pass 2: åtgärd och säkerhetsgräns

- Ny `_read_lines(root,relative,allow_missing=...)` använder den redan granskade strikt allowlistade `_manifest_parts` och POSIX `_manifest_open_flags` från `core.selfdev_workspace`.
- Projekt-/stagingroten och alla underkataloger öppnas via `O_DIRECTORY|O_NOFOLLOW` med `dir_fd`. Slutfilen öppnas `O_RDONLY|O_NOFOLLOW|O_NONBLOCK` via samma fd, och `fstat` kräver vanlig fil med en enda länk.
- Bytes läses under fast **2 MiB per fil**, med absolut avvisning om storleken överskrids. `fstat` före/efter upptäcker storleks-, inode-, mtime- och ctimeförändringar under läsningen. UTF-8 måste vara giltig; max 20 000 rader per fil.
- Högst **8 MiB käll-/stagingbytes totalt** tillåts i en granskningsrapport. Ett överskridande ger fel i stället för att presentera en potentiellt missvisande trunkerad diff. Ordinarie `max_diff_chars` styr fortfarande avkortning av det slutliga diffsvarsformatet.
- Endast kända additions/deletions ger `allow_missing=True`. Försvunnen ändrad fil, ompekad länk och otillåtna namn gör att granskningen misslyckas stängt.
- Sex nya tester: slutfilslänk byts efter manifest, kataloglänk byts efter manifest, överskriden filgräns, överskriden aggregatbudget, försvunnen ändrad fil och ogiltig outputgräns.

## Revisionsstatus och återstående risker

- Detta skyddar read-only granskningens indatafångst, **inte** hela releasebeslutet: legitima filer kan muteras efter diffen men före nästa verifieringssteg; alla promotionsspärrar måste bygga på slutlig hash/behörighetskontroll.
- `difflib.SequenceMatcher` har fortsatt databeronde CPU-kostnad även med begränsade indata. Operativ timeout/sandbox är inte ett fullständigt OS-skydd.
- Icke-stödda Windows/POSIX-plattformar avvisas i stället för osäker fallback. Symboliska länkar i redan betrodd rotförälder, bind mounts, flytt av öppnad inode, lokala privilegier och extern kodändring kräver OS-behörighetsmodell.
- `core/selfdev_promote.py` journal-/backup- och rollback-deletionsvägar använder fortfarande pathname-baserade delar; åtgärden från PR #280 rör **bara** `_atomic_copy` och motsvarande destination/bytes-verifiering. Behörighetsgränser och recovery behöver ytterligare genomgång.
- Slutlig fysisk VENTUNO-verifiering, beroende-/licens-SBOM, Linux/Qualcomm-firmware, fullständig manuell filgranskning och main/deployment-gate är fortsatt NO-GO.

**Verifieringskrav:** GitHub-hostad/source-only full ARM64-projektsvit på exakt sista commit. Inga aktiva källfiler, modeller, mikrofoner eller nätanslutna prylar påverkas av DRAFT.
