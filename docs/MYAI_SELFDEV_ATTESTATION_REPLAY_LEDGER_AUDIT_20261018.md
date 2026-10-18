# MyAI: uppdaterarägt engångsregister för signerade verifieringsbevis (prototyp)

**2026-10-18.** Bygger på DRAFT PR #333 (bb7a7db47c5067d3c1ae6135c8efde8b91c6a1b7), som införde en ren Ed25519-kontroll av signerade bevis.

## Problemet

En giltig signatur ensam garanterar inte att en äldre, giltig verifiering inte spelas upp igen. En inskickad lista över redan använda nonce-värden hjälper bara om den är betrodd, beständig, skyddad mot manipulation och läses under samma transaktion som det nya godkännandet. Den gamla lokala `verification.json` är fortfarande osignerad och kan påverkas av samma-UID-skrivare. Ingen oberoende verifieringstjänst finns ännu, och någon verklig updater-UID har inte installerats på VENTUNO.

## Genomförd avgränsad implementation

`core/selfdev_attestation_replay.py` tar endast emot **en redan öppnad SQLite-anslutning från anroparen**. Modulen väljer aldrig en OS-sökväg, läser inte hemligheter, genererar inga privata signeringsnycklar och anropar inte `SelfDevPromotionManager`. Databasen ska i en framtida implementation **ägas av den separat privilegierade updater-processen**; det skapas inte av denna PR.

- Updatern utfärdar en slumpmässig 128-bitars nonce via `secrets.token_hex(16)`, knuten i databasen till session, manifest-SHA256, testplan-SHA256, verifieringsbevisets SHA256 och giltighetstid på högst fem minuter. Testerna kan injicera en deterministisk nonce-fabrik, aldrig produktionsanvändare.
- Utfärdande gör `INSERT` under `BEGIN IMMEDIATE` med nonce som primärnyckel; duplikat avvisas atomiskt.
- Konsumtion gör `BEGIN IMMEDIATE`, läser **den redan lagrade betrodda kontexten**, verifierar Ed25519-signaturen från #333 mot utifrån tillförd pinnad publik nyckel och uppdaterar `consumed_unix` med villkoret `IS NULL`, allt före `COMMIT`.
- Ogiltig signatur, fel session/manifest/testplan/bevis/nonce, för tidig eller för sen förfrågan, okänd, förbrukad eller kolliderande nonce ger undantag och `ROLLBACK`, aldrig ett falskt lyckat kvitto. Returtyperna anger uttryckligen `authorizes_mutation=False` och `production_deployment_authorized=False`.
- Tester använder tillfälliga SQLite-databaser samt privata **engångstestnycklar**. De verifierar att ett förbrukat bevis nekas efter stängning och återöppning av databasen, att två anslutningar ser samma förbrukade tillstånd, att felaktiga signaturer inte förbrukar nonce samt att felaktig kontext avvisas.

## Viktig skillnad mellan testad återöppning och verklig hållbarhet

En lyckad återöppning i testmiljön visar att använd nonce lagras i SQLite under normal drift. Den **bevisar inte** överlevnad vid fysisk eMMC-strömförlust, filsystemskorruption, rollback/snapshot av databasen, extern databasersättning, oförutsedda SQLite-journalinställningar eller krasch under en flerkomponents-promotion. Separat DAC/ACL och skydd mot återställning av gamla databasögonblick behövs fortfarande. Två anslutningars sekventiella provning garanterar inte alla möjliga konkurrensscenarier under fysisk last.

Inte heller finns en oberoende verifierare som själv observerar Bubblewrap-körningarna och äger en hemlig signeringsnyckel. Att låta MyAI:s mindre privilegierade runtime själv välja bevis-SHA eller signera `passed=True` skulle kringgå säkerhetsmodellen. Uppdaterarens signerade och konsumtionsregistrerade **inspektionskvitto** är fortfarande uttryckligen inte en tillåtelse att ändra kod.

## Fortsatta blockeringar

1. Migrering av VENTUNO-runner från `arduino` till separat säkert konto; GitHub-runnergrupp och gamla auto-triggade arbetsgrenar måste hanteras administrativt.
2. Betrodd oberoende verifierings-UID, säkert IPC-protokoll, skyddad signeringsnyckel och oberoende råtestbevis.
3. Updater-ägd SQLite-fil med korrekta katalogrättigheter, separat UID, WAL/journalstrategi, backup/anti-rollback och fysisk power-loss-/recovery-verifiering.
4. Integrerad promotion får inte kopplas in förrän testerna och säkerhetspolicyn är godkända. Full SBOM/licens/ABI, NPU och ljudtest kvarstår.

**DRAFT och NO-GO.** Endast GitHub-källkodsändringar och syntetiska lokala/hostade tester. Ingen faktisk VENTUNO-hårdvara, service, användare, hemlighet, release eller main-merge berörs.
