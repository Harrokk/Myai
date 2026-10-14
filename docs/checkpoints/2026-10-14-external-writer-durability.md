# MyAI checkpoint — externa kodändringar och skrivdurabilitet (2026-10-14)

## Aktuell utvecklingspunkt
- Branch: `dev/selfdev-external-writer-durability-20261014`
- Draft PR #126: https://github.com/Harrokk/Myai/pull/126
- Bas: `dev/selfdev-global-lock-20261014`, draft PR #125.
- All kod är fortfarande utkast; inget är sammanslaget i main eller installerat på aktiv VENTUNO.
- Självuppdatering/promotion är fortsatt avstängd i produktionskonfigurationen.

## Hittade fel
1. Föregående projektlås `runtime/selfdev/.promotion.lock` blockerade samverkande MyAI-sessioner men inte externa editorer/processer. Efter preflight kunde extern kodfil ändras innan en oförbehållsam `os.replace` skrev över den.
2. `_atomic_copy` skrev en temporär fil och bytte namn utan att uttryckligen fsync:a filen och dess moderkatalog. Journalen kunde bli mer beständig än kodfilsbytet vid verkligt strömavbrott.
3. Efter ett misslyckat filbyte försökte den vanliga rollback-vägen återställa alla ändrade filer utan att först säkerställa att en extern process inte redan skrivit nytt innehåll.
4. SHA-256 för staging beräknades på nytt efter preflight i stället för att låsas till den godkända manifest-snapshoten.

## Ändringar i PR #126
- Originalversioners SHA-256 sparas i prepared-journalen; nya SHA-256 hämtas från verifierat staging-manifest.
- Stage bytes kontrolleras efter preflight samt omedelbart före varje kodbyte; kopierat resultat verifieras mot avsett manifest.
- Före `os.replace` kontrolleras att befintlig målkodfil matchar original SHA-256 (eller saknas om filen är ny). Om extern ändring upptäcks avbryts promotion.
- Vid ordinarie fel kontrolleras alla berörda målfiler. Vid okänt innehåll lämnas prepared-journal och innehåll orört för en uttryckligt godkänd manuell recovery, i stället för att tyst skriva över en extern ändring.
- Temporära kodfiler fsync:as före rename och moderkatalogen fsync:as efteråt. Säkerhetskopior och relevanta kataloger synkroniseras före prepared-journalen; nya filer som tas bort vid rollback synkroniseras.
- Säkerhetskopieringsfel före journalen städar ofullständig backup utan att röra live-kod.
- Befintliga avbrottstest-dubblar uppdaterades att acceptera förväntad-SHA-kontrollens keyword-argument.

## Bekräftade tester
- Första utkastet: felaktigt – befintliga avbrottstest-dubblar träffade backup-steget och senare metodsignaturen. Detta korrigerades; ingen produktion påverkades.
- Efter korrigering: full VENTUNO ARM64 CI run 38534470134, 1543 passed / 6 skipped.
- Sista förbättringen: verifierat staging-manifest och rollback-fsync samt två nya testfall.
- **Sista fulla lyckade källkodskörning**: https://github.com/Harrokk/Myai/actions/runs/38534695175 — **1545 passed, 6 skipped**.
- Sju nya regressionstester kontrollerar bland annat extern edit före ett filbyte, extern edit av andra filen, extern edit av redan uppdaterad fil före felrollback, fil- och katalog-fsync, backup-skrivfel, staging-modifikation efter preflight och simulerad katalog-fsync-fel efter rename.
- De sex överhoppade är host-only ONNX/NumPy-tester. Tidigare separat Github-hostad x86 testkörning: https://github.com/Harrokk/Myai/actions/runs/38520039444 — 22 pass.

## Utestående risker och spärrar
- Hashkontroll följd av os.replace ger fortfarande ett litet TOCTOU-fönster om extern icke-samarbetande process skriver exakt efter sista kontrollen. Kernel-låset är advisory, inte OS-tvingande lås för all programvara.
- Simulerad `SystemExit`, I/O-fel och mockade externa skrivningar bevisar **inte** att strömavbrott på riktig VENTUNO/eMMC ger återställningssäkerhet. Fysisk power-loss, eMMC-cacher, journalfilsystemets semantik och flerprocess-race måste granskas innan obevakad självuppdatering kan godkännas.
- Självuppdatering ska därför förbli avstängd i aktiv MyAI; utkasten #112, #113, #114, #115, #116, #119, #120, #122, #123, #124, #125, #126 väntar fortfarande på granskning/sammanslagning.
- Den separata GitHub Support-frågan med historiskt cachelagrat SQLite-minne enligt blocker-PR #110 kvarstår. Inga historiska hemliga SHA behöver upprepas.
- Användaren har pausat Windows/Arduino App Lab IP-felsökning. Inga USB/mikrofon/ljud/Bluetooth-kopplingar, kamera, STM32, NPU eller aktiva tjänster har ändrats.
