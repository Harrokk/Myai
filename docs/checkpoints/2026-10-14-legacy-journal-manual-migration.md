# MyAI checkpoint – manuell migrering av äldre journaler och återställning över flera avbrott

**Datum:** 2026-10-14
**Utvecklingsgren:** `dev/selfdev-legacy-journal-migration-20261014`
**Verifierat commit:** `6882c4dda5217299557efb46c659e8046a1094a1`
**Draft PR #128:** https://github.com/Harrokk/Myai/pull/128
**Baserad på:** PR #127 `dev/selfdev-journal-integrity-20261014`.

## Vad som ändrats
1. Äldre HMAC-lösa `promotion.json` kan inte användas direkt i nuvarande recovery/rollback, för att inte godta en manipulerad journal. Ny **manuell** `SelfDevPromotionManager.migrate_legacy_completed(promotion_id, 'MIGRATE LEGACY <session_id> <promotion_id>')` kräver exakt fras, öppnad selfdev+promotion-konfiguration, auditering och projektgemensamt mutation-lås. Metoden ändrar aldrig aktiva källkodsfiler.
2. Endast historiska journaler med verifierbart slutförd promotion får migreras; unsigned `prepared`, `rollback_prepared`, redan rollbackade, delvis skrivna, felidentifierade eller journaler med felaktiga sökvägar och hashes nekas. Original- och målfilers metadata samt verkliga målfiler och säkerhetskopior jämförs före underskrift.
3. Ursprungliga osignerade journalbytes sparas till en privat, fsynkad, exklusivt skapad `promotion.legacy-unsigned.json` före HMAC-signering. Ett avbrott mellan arkivering och signering kan återupptas med samma exakta migrationsfras endast om arkivet matchar de kvarvarande ursprungliga bytesen.
4. Säkrare backup-sökvägar: symlänkar på målet eller i dess katalogkomponenter, och säkerhetskopior med flera hårdlänkar, avvisas av recovery, vanlig rollback och migrering. Hashkontroll kvarstår.
5. Ett extra `SystemExit` mitt under återställning av flera kodfiler simulerades; nästa manuella recovery fortsätter från de redan återställda originalfilerna.

## Verifiering
- Fullt regressionstest på **riktig VENTUNO Q ARM64 GitHub self-hosted runner** i *isolerad temporary checkout*: https://github.com/Harrokk/Myai/actions/runs/38538372289
- **1561 passed, 6 skipped**, alla Python-källfiler kompilerade.
- Sju nya tester: legacy completed + manuell fras + rollback, vägran att migrera unsigned avbruten uppdatering, förfalskade hashes och nya användarändringar, backup-symlink/hardlink, hardlink i normal rollback, migreringsavbrott och säkert omförsök, och andra avbrottet mitt under recovery.
- Ett äldre test behövde uppdateras för den nya, mer generella feltexten för skadad backup, men säkerhetskontrollen är bevarad.
- Sex optional host-only ONNX/NumPy-fall hoppas över på ARM64-runnermiljön. Separat x86 runner med 22 godkända tester: https://github.com/Harrokk/Myai/actions/runs/38520039444.

## Mycket viktiga begränsningar
- Att återbekräfta byteinnehållet och hashvärdena i en osignerad historisk journal **bevisar INTE dess historiska äkthet**. Administratören måste själv ha en betrodd referens för journalen innan migreringsfrasen används. Funktionen är explicit och får aldrig kopplas till automatisk migrering/acceptans av `prepared`-journaler.
- Ny HMAC-nyckel skyddar inte mot en angripare som också kan skriva/läsa nyckelfilen under samma användarkonto. Behörighetsisolering behövs för sådan hotbild.
- Directory-fsync och simulerade strömavbrott på temporära filer är inte validering av riktig plötslig strömförlust, eMMC-driverns cache och filsystemsegenskaper.
- Advisory projektlås hindrar samverkande MyAI-processer, inte icke-samverkande editorer. SHA-kontroll före `os.replace` har kvar ett kort TOCTOU-fönster.
- Alla ändringar finns i separata draft PR #112, #113, #114, #115, #116, #119, #120, #122, #123, #124, #125, #126, #127, #128. Inga av dessa är installerade i den aktiva MyAI-versionen. Självuppdatering förblir avstängd.
- GitHub Support-historikfrågan enligt PR #110 är fortfarande en blockerare för main-merge.
- Ingen aktiv MyAI/GenieX-tjänst, användarfil, mikrofon, kamera, Bluetooth-parning, STM32, NPU, Windows-terminal eller fysisk hårdvara ändrades/testades i detta arbete.

## Nästa autonoma kandidat
Läsbar säkerhetsrapport / offline bedömning av gamla journaler utan några filmutationer; ytterligare felinjektion runt journaluppdateringar och backups; granskning av auditering och avsaknad av privilegieseparation, innan någon sorts produktionsrelease.
