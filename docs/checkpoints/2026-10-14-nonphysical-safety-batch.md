# MyAI — säkerhets- och CI-checkpoint för allt arbete utan fysisk kontroll
**Datum:** 2026-10-14
**Aktuell utvecklingsgren:** `dev/combined-static-ci-audit-20261014`
**Senaste gröna kodcommit:** `914e76cd34668fe9515b84b6611540ec14714a73`
**Releasebeslut:** Ej driftsättningsklar. Inga draft-PRs mergade till main. Ingen kod installerad i aktiv MyAI eller GenieX. Självuppdatering/auto-promotion är avstängd.

## Genomförda nya isolerade utkast

| PR | Säkerhetsändring | Isolerat CI-resultat |
|---|---|---|
| [#136](https://github.com/Harrokk/Myai/pull/136) | Processgemensamt POSIX `flock` kring JSONL append + rotation; låsinode verifieras och 10 sekunder är max väntan | [1603 passed, 6 skipped](https://github.com/Harrokk/Myai/actions/runs/38548835619) |
| [#137](https://github.com/Harrokk/Myai/pull/137) | Kontrollerar audit leaf-inode före/efter skrivning; obligatorisk audit fsync:ar fil och moderkatalog och nekar åtgärd på fel | [1608 passed, 6 skipped](https://github.com/Harrokk/Myai/actions/runs/38549319908) |
| [#138](https://github.com/Harrokk/Myai/pull/138) | Avvisa grupptillgängliga skrivbara loggkataloger; begränsa loggläsning till 8 MiB och rotationskopior till 128 | [1614 passed, 6 skipped](https://github.com/Harrokk/Myai/actions/runs/38549862645) |
| [#139](https://github.com/Harrokk/Myai/pull/139) | Lägg till befintlig source-only statisk audit som obligatorisk steg i ordinarie Ventuno testworkflow | [1614 passed, 6 skipped, audit PASS](https://github.com/Harrokk/Myai/actions/runs/38550283305) |

Totalt 16 nya regressionstester från #135 till #139 utöver tidigare 1598 godkända vid PR #135: 5 nya #136, 5 nya #137, 6 nya #138, inga extra i #139; senaste fullsuite har **1614 passed, 6 skipped**. Multiprocess-testfall kör faktiska separata OS-processer. Filerna skapas under pytest-temp i en staging checkout på GitHub Actions self-hosted VENTUNO ARM64 runner. Full testning på hårdvaran av produktionsmoduler eller faktiska strömavbrott har *inte* gjorts.

## Statisk source-only granskning, senaste commit
- Resultat: **PASS, 0 blockerande fynd**.
- **424 tracked files**, varav **328 Python-filer** med giltig AST, **149 testfiler**, **1485 testfunktioner**, **47 workflows**, **2 JSON-filer** med giltig syntax.
- **1 manuell flagga:** `tests/test_ventuno_whisper_base_swedish_comparison.py:202` har `exec(compare._METRIC_SOURCE, namespace)`. Detta anrop används i en testhjälpfunktion för en statisk intern metrikkälla; det är ingen observerad produktionsexekvering av användarinmatning. Flaggan ska behållas för kodgranskning (ingen automatisk "godkänn allt"-klassning).
- Audit verifierar bl.a. att känsliga `memory.db` inte spåras, att konfigurationsflaggorna för mic/kamera/location/terminal automation och selfdev är avstängda, att JSON är giltig och att inga privilegierade workflow-triggers finns.
- Source-only script `scripts/static_repository_audit.py` behöver inte fysisk åtkomst och importerar inte MyAI:s programmoduler.
- GitHub-hostad separat x86-testkörning för 6 optional ONNX/NumPy-case finns sedan tidigare (22 pass): https://github.com/Harrokk/Myai/actions/runs/38520039444. Dessa 6 hoppas över på VENTUNO p.g.a. frånvarande paket.

## PR-integration och historikrisk
- GitHub API rapporterade **29 öppna draft PRs**, inklusive den äldre alternativa kedjan [#117](https://github.com/Harrokk/Myai/pull/117), [#118](https://github.com/Harrokk/Myai/pull/118), [#121](https://github.com/Harrokk/Myai/pull/121). De ändrar delvis samma minnes/workspace/selfdev-kod som den senare aktiva draft-kedjan #119,#122,#123,#124 etc. Dessa alternativa PRs bör jämföras, inte köras in parallellt utan konfliktgranskning.
- Stacked aktiv kedja till PR #139 går tillbaka genom #135, #134, #133, #132, #131, #130, #129, #128, #127, #126, #125, #124, #123, #122, #120, #119, #116, #115, #114, #113 och #112. Alla PRs är fortfarande *draft*.
- [Blocker-PR #110](https://github.com/Harrokk/Myai/pull/110) är alltjämt *open/draft*. Historiska branch/tag refs har skrivits om, men GitHub Support har ännu inte i det åtkomliga underlaget bekräftat att gamla dangling/cacheade känsliga objekt är purgade. Ingen hemlig gammal SHA publiceras här. **Ingen main-merge före Support-purge eller separat uttryckligt riskbeslut.**
- Main commit vid kontroll: `f125fe6dc9abd6b27747f86d440fbb77b0602e58`, oförändrad av denna omgång.

## Kvarstående icke-fysiska risker som kräver särskild design eller granskning
1. Processgemensamt POSIX `flock` skyddar endast samverkande processer; en illvillig process med samma UID och åtkomst till loggmappen kan ännu byta loggposter inom en fixerad directory-fd efter sista kontrollen. Endast ändrad OS-behörighetsgräns/privilegieseparation kan ge starkare isolering. Race är minskade och kan detekteras i testade fall, men inte fullständigt omöjliggjorda.
2. HMAC-nyckeln till selfdev-journalen är fortfarande projektlokal och tillgänglig för samma UID. Ett adversarialt program med den identiteten kan ändra både nyckel och journal. Nyckelrotation/separat tjänstanvändare och privilegier kräver separat migrations- och driftsdesign.
3. Windows fallback för loggarna saknar POSIX dirfd/flock-garantin. Målmaskinen VENTUNO är Linux ARM64, men Windows-beteendet ska inte beskrivas som likvärdigt.
4. Obligatorisk audit fsync + metadata-kontroller är bättre före skrivåtgärd men säkerställer inte att eMMC i praktiken överlever plötslig strömförlust; disk/cache/filsystem kan skilja sig. Ingen fysisk power-cut-test utförd.
5. Journalmigrering av tidigare osignerade objekt förutsätter autentisk extern proveniens och aktiv manuell godkännandefras. Okända osignerade eller partiella journals nekas.
6. Det finns ännu ingen plan för att säkert automatiskt ta bort föräldralösa `.verified-backup-*.tmp` utan manuell förhandsgranskning; inventering är read-only med avsikt.
7. CI använder temporär källkodscheckout och aktiv Ventuno-Python-venv för att köra pytest men kör inte script som installerar, startar om eller modifierar produktion. Källkodsläsning/CI är inte samma sak som produktionshårdvaruverifiering.

## Fysiska och externt blockerade punkter (ej utförda)
- Strömavbrotts-/eMMC-cache-fault-test med faktisk omstart, långvarig stress, live CPU/NPU/QNN inferens, ljudupptagning, mikrofontest, BLE parning, kamera, STM32 och nätverksdiagnostik i Arduino App Lab. Även rent skrivskyddade hardware-diagnostiksteg hålls här utanför användarens önskan om inga fysiska kontroll/test.
- GitHub Support-rensning av server-side gamla cacheade objekt kräver GitHubs respons; kan inte verifieras eller slutföras genom att bara ändra repo-kod.
- Mergning av draft-PRs, driftsättning, promotion och tjänstestarter lämnas avsiktligt orörda.

## Fortsättningsprincip
Den här grenen är en verifierad **kod-/CI-checkpoint**, inte en release. Inget automatiskt bakgrundsarbete är schemalagt. Vid fortsatt utveckling: jämför alternativt PR-träd, granska kvarstående leaf-race och OS-behörighetsdesign, samt avvakta fysisk och GitHub Support-verifiering innan produktionsauktorisation.
