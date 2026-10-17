# MyAI – projektglobalt selfdev-lås: no-follow-katalogankring (2026-10-17)

**Bas:** PR #288, commit `effc67ce07102c0e86fd24b0055a636239fd9751`. **Gren:** `dev/manual-audit-selfdev-promotion-lock-dirfd-20261017`. Inga produktionstester, inga ändringar på installerad VENTUNO.

## Pass 1 – inventerat kontrollflöde

`SelfDevPromotionManager._project_mutation_lock()` låser alla kooperativa promotion-, rollback- och recovery-operationer med en icke-blockerande OS-flock (eller msvcrt på Windows). Låsfilen `runtime/selfdev/.promotion.lock` genomgick `_private_selfdev_directory()` och öppnades sedan via `os.open(str(lock_path),O_NOFOLLOW)`. Även om slutfilens symlänksföljning spärrades kunde förälderkatalogen ompekas mellan den separata säkerhetskontrollen och filöppningen.

## Pass 2 – kodändring

- Låsfilens föräldrar öppnas nu med `_pinned_parent(lock_path)`, vars `O_DIRECTORY|O_NOFOLLOW` avvisar symlänkar i varje katalogled.
- Den öppnade kataloginode kontrolleras via `os.fstat`: katalog, egen UID och inga grupp-/världsskrivrättigheter. Slutlig låsfil öppnas med `O_CREAT|O_RDWR|O_NOFOLLOW` och med `dir_fd` relativt samma katalog.
- Tidigare validering av filtyp, UID, en enda hårdlänk och exklusivt privat fil-läge bevaras. Själva `flock(LOCK_EX|LOCK_NB)` och release via den låsta filbeskrivaren ändras inte.
- Tre syntetiska tester: byte av förälderkatalog till extern symlänk före öppning blockerar lock, byte av alias direkt efter låsfilens öppning leder inte till att extern låsfil används, redan symlänkad slutfil avvisas.
- Befintliga regressioner för osäkra låsfilbehörigheter, hårdlänkar, dubbla promotion-/rollback-initiativ samt avbrotts-/återställningsflöde körs i full ARM64 source-only CI.

## Kvarstående risker / NO-GO

- Advisory-flock gäller låsfilens **inode**. En privilegierad eller lokalt skrivbehörig process kan byta ut själva selfdev-katalogen, skapa en annan lock-inode och bryta samordningen mellan två processer som öppnar olika inoder. Denna PR hindrar omdirigerad filöppning men ger **inte** ett oersättligt globalt projektlås; UID-/katalogisolering krävs.
- `_private_selfdev_directory(create=True)` innehåller fortfarande path-baserat skapande av `runtime/selfdev`. Att skapa kataloger under obetrodd, delad förälder kräver separat OS-säkerhetsgranskning och en processägarmodell.
- HMAC är inte oberoende release-signering. Fysisk återställning efter verkligt strömavbrott, komplett kod- och beroendegranskning/SBOM, firmware/ABI samt ljud/NPU på VENTUNO är ej slutförda.
- Ingen merge till main, ingen automatisk självmodifiering, ingen aktiv installation eller återställning. Kräv full ARM64 source-only CI på exakt HEAD.

