# MyAI checkpoint — updater-gräns, replay-kontroll och engångscontainer (2026-10-14)

**Sparad utvecklingsgren:** `dev/selfdev-disposable-uid-boundary-ci-20261014`
**Verifierat kod-commit:** `12b4fa865bf259cc08afb0c9dbc88fea83e87960`
**Installation:** Ingen. Inga main-merger, inga produktionsfiländringar, ingen omstart, inga installerade OS-användarkonton och ingen aktivering av självuppdatering.

## Tre nya utkast

### [PR #141](https://github.com/Harrokk/Myai/pull/141) — strikt inspektionsprotokoll, endast offline
- Gren `dev/selfdev-offline-admission-protocol-20261014`, stackad på #140.
- Ny ren modul `core/selfdev_request_protocol.py` med tydligt icke-privilegierat `inspect_candidate`-API.
- Accepterar högst 32 KiB UTF-8 JSON, en låst fullständig lowercase Git-commit SHA, utgångstid högst 5 minuter framåt och upp till 32 sorterade källkodsfilnamn med korrekta SHA-256-hashar.
- Stoppar extra fält, falska godkännanden, promotion/recovery/restart-kommandon, dubbla JSON-nycklar, ogiltiga tal, osäkra sökvägar, symlänksliknande traversal/hidden paths, avslutande snedstreck och namn som kolliderar på skiftlägesokänsliga filsystem.
- Resultat bär alltid `authorizes_mutation=False` och `requires_human_approval=True`. Jämförelse sker endast på inmatade bytes i minnet: även positivt resultat är `bytes_match_untrusted`, aldrig verifierad källa eller installationsgodkännande.
- En ursprunglig regression hittade `core/example.py/` som tilläts efter Path-normalisering. Detta ändrades uttryckligen; sista testsvit [run 38556445886](https://github.com/Harrokk/Myai/actions/runs/38556445886) **1679 passed, 6 skipped**, statisk audit PASS.

### [PR #142](https://github.com/Harrokk/Myai/pull/142) — SQLite-baserad replay-prototyp för granskningsbegäranden
- Gren `dev/selfdev-inspection-replay-ledger-20261014`, stackad på #141.
- `core/selfdev_preview_ledger.py` lagrar använda preview-begärande-ID:n med SQLite `BEGIN IMMEDIATE`, `synchronous=FULL` och unik nyckel. Samverkande separata processer och trådar kan inte räkna samma ID som nytt.
- Rapporterar `already_seen`, `request_id_conflict`, `expired` eller `recorded_for_inspection`; **samtliga** tillstånd nekar mutation och kräver fortsatt mänskligt godkännande.
- Testar privata filrättigheter, symlänkar/hårdlänkar, skadad SQLite, gruppskrivbara kataloger, multiprocesser och trådar.
- Den första körningen stoppade en testfixture vars skadade SQLite-fil hade för öppna rättigheter (säkerhetskontroll fungerade). Efter att testfilen gjorts privat: [run 38557209442](https://github.com/Harrokk/Myai/actions/runs/38557209442), **1690 passed, 6 skipped**, statisk audit PASS.
- Detta är endast en preview-ledger på temporära testdatabaser. Den kan inte ge skrivbehörighet, validerar inte peer UID och skyddar inte mot en same-UID-angripare.

### [PR #143](https://github.com/Harrokk/Myai/pull/143) — test av två isolerade UID:er i en engångscontainer
- Gren `dev/selfdev-disposable-uid-boundary-ci-20261014`, stackad på #142.
- Github-hostad Ubuntu-jobb startar en **disposable Docker** med nätverk avstängt, skrivskyddat rotfilsystem och volatil `/tmp`; endast testscript monterat read-only. Imagen är SHA256-digest-pinnad enligt workflow, Linux capabilities minimiserade till CHOWN/FOWNER/SETUID/SETGID och `no-new-privileges` aktiverat.
- Testscript kräver uttrycklig container-markör, skapar enbart **fejkad** nyckel och testfiler, och testar två Unix-UID:er efter `setuid`: runtime 23002 får läsa publik kod men kan inte ändra kod eller öppna updater-only staging/key/audit; updater 23001 får endast avsedda simulerade updater-rättigheter.
- Ingen verklig VENTUNO-användare, systemd-enhet, produktionslogg, produktionsnyckel eller kod har ändrats.
- Ursprungligt workflow med marketplace-checkout startade inte; direkt hämtning av exakt commit löste detta. Den första mer begränsade capability-körningen stoppade fixturesetup efter ägarbyte; ordningen rättades och användning av Docker tmpfs gör destruktiv städning onödig.
- Slutlig hosted Docker körning [run 38558553927](https://github.com/Harrokk/Myai/actions/runs/38558553927) **PASS**: `runtime=denied_privileged_write_read`, `updater=simulated_permissions_only`, `production_touched=false`, `container_discarded=true`.
- Full isolerad VENTUNO ARM64-run [38558553850](https://github.com/Harrokk/Myai/actions/runs/38558553850): **1690 passed, 6 skipped**, statisk granskning PASS med 0 blockerande fynd, 437 spårade filer och en tidigare dokumenterad manuell testflagga.

## Avgörande gräns mellan verifierat och ej verifierat

**Verifierat utan fysisk åtkomst:**
- JSON- och manifestvalidering, icke-auktoriserande dataklasser och rent bytehash-test.
- SQLite-deduplicering av preview-ID:n även för oberoende arbetande processer i temporära testdatabaser.
- Linux-kärnans grundläggande användar-/filrättigheter för två skilda UID:er i ett avskilt Docker-test.
- Full VENTUNO ARM64-källkodstest och återkommande statisk repo-audit, utan att installera eller köra produktion.

**Inte verifierat eller implementerat:**
- Aktuell MyAI/GenieX kör **inte** under de nya UID:erna på VENTUNO och är inte flyttad till ett privilegieseparerat upplägg.
- Ingen skarp autentiserad IPC, signerad Git/artifact-proveniens, skyddad utplaceringsmekanism, human-approval ledger eller atomisk versionskatalog-release är införd.
- Den separata SQLite-ledgern är inte ett godkännandesystem; både runtime och updater kan fortfarande missbrukas om samma system-UID eller osäkra kataloger delas.
- Ingen faktisk eMMC power-cut/USB audio/Bluetooth/camera/NPU/STM32-feltest, ingen tjänstomstart och ingen Windows Arduino App Lab IP-kontroll.
- GitHub Support-purge av tidigare historiskt cacherelaterade känsliga objekt är **fortfarande inte bekräftad**; äldre [PR #110](https://github.com/Harrokk/Myai/pull/110) ligger kvar som release-blocker.
- Alla berörda PR:er är fortfarande draft; `main` och aktiv VENTUNO-installation är oförändrade. Automatisk promotion förblir avstängd.

## Nästa tillåtna icke-fysiska steg
1. Offline validering av signerad byggartefakt/release-manifest och strikt peer-credential-IPC (som **inte** får kopplas till skarpa selfdev-mutationer).
2. Egen ansvarsmodell för root/updater/runtime, behörighetsmatris, permanent approval replay-lagring och revisionslogg för privilegierade uppdateringar; måste granskas oberoende innan migration.
3. Statiskt samla PR-stacken och testutvärdera framtida merge-konflikter utan att göra faktiska merger. Inga automatiska integrationer med PR #117/#118/#121 eller rensningar av känsliga historiska GitHub-objekt.
4. Separat fysisk testplan och operativ releasegodkännande innan några systemkonton, tjänster eller källkod aktiveras.
