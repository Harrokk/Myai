# MyAI – legacy-journalens arkiv: förankrad, icke-överskrivande publicering (2026-10-17)

**Bas:** PR #302 (`f89bd181558e1ddbb670d365daa3e63d2359972d`). Allt är DRAFT; inga aktiva migrationer, återställningar eller filer på VENTUNO ändras.

## Pass 1 – logik och identifierad risk

`_migrate_legacy_completed_impl` läser en äldre osignerad journal under manuell godkännandefras, kontrollerar den mot aktiv kod och skapar `promotion.legacy-unsigned.json` med originalbytes innan en HMAC-signerad journal skrivs. Den tidigare arkivlogiken körde `archive.is_symlink()`, `os.path.lexists()`, `archive.lstat()` och `archive.read_bytes()` på skilda pathname-uppslagningar. Vid ny fil öppnades `os.open(str(archive), O_CREAT|O_EXCL|O_NOFOLLOW)` med endast slutfilens symlänkspärr. En lokalt skrivbehörig skribent kunde byta **förälderkatalogen** mellan kontroller och läsning/skrivning, och läsa från eller skapa arkiv i ett annat träd.

## Pass 2 – säkerhetsändring

En ny `_publish_or_verify_legacy_archive(rollback_root,raw)` ersätter pathname-arkivsekvensen:

- Kräver `raw` av typen bytes, högst 1 MiB, vilket överensstämmer med den tidigare signerade journalläsningens gräns.
- Öppnar alla föräldrar via `_pinned_parent` (`O_DIRECTORY|O_NOFOLLOW`) och kontrollerar verklig rollbackkatalog med `fstat`: rätt UID och ingen grupp-/världsskrivning.
- För befintligt arkiv öppnas sista komponenten med `O_RDONLY|O_NOFOLLOW|O_NONBLOCK` via **samma** katalogfd. Innehållet accepteras endast för vanlig fil, nlink=1, rätt UID, privata permissions, rätt storlek, byte-identiskt innehåll och stabilt `fstat` före/efter läsning. Inget befintligt arkiv skrivs över eller repareras.
- För ny fil används `O_CREAT|O_EXCL|O_NOFOLLOW`, mode 0600 och dirfd, varefter bytes skrivs, filen fsync:as och förälderns dirfd fsync:as. En konkurrerande skapning av samma namn avvisas.
- Fem nya tester: byte av rollback-katalogalias **efter** exklusiv arkivöppning; utbyte av förälder **före** öppning; befintlig slutsymlänk; existerande hårdlänk eller skadade bytes; osäkra arkivbehörigheter. Tidigare idempotent migrationsretry och recovery-regressioner ingår i full CI.

## Fortsatta risker och NO-GO

- Arkivets nyskapande följt av separat signering är inte en atomär transaktion mot en privilegierad lokal skribent; verklig strömavbrottstestad konsistens återstår. Vid skrivfel kan en partiellt skriven, icke överlagringsbar arkivfil kvarstå och kräva **manuell** granskning, hellre än tyst reparation.
- HMAC-nyckeln skyddar mot oavsiktlig/obehörig journalmodifiering inom samma UID-modell, men är inte oberoende signerad releaseproveniens. Utbytta kataloginoder av en icke-samarbetande writer kräver fortsatt UID-/ägarskapsisolering.
- Fullständig fil-för-fil-revision, beroende-/licens-/SBOM-kontroll, NPU/ljud och fysisk VENTUNO-återställning efter strömavbrott är fortfarande öppna spärrar. Ingen merge till main eller aktiv installation.

**Verifiering:** full ARM64 source-only suite på exakt slutlig HEAD.
