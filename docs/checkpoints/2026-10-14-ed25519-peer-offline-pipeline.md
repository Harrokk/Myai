# MyAI checkpoint — signerad offline-inspektion och Linux peer identity

**Datum:** 2026-10-14
**Senaste utvecklingsgren:** `dev/offline-inspection-pipeline-20261014`
**Senaste kodändringar:** signerad inspektionsmanifestverifierare, kernel-ID-kontroll och sammansatt offline testflöde.
**Tillstånd:** Alla delar är fortsatt GitHub DRAFT. Ingen produktionsinstallation, PR-merge, OS-användarändring, ny systemd-tjänst eller aktivering av självuppdatering har utförts.

## PR #144 — signerad inspektionsmanifest, endast förhandsgranskning
- [PR #144](https://github.com/Harrokk/Myai/pull/144), gren `dev/offline-signed-preview-20261014`, baseras på #143.
- Ren verifierare `core/selfdev_signed_manifest.py` för Ed25519 med domänseparerad canonical JSON-signatur: `myai:inspection-only:ed25519:v1`.
- En signerare accepteras bara om dess 32-byte Ed25519 *publika* nyckel lämnats av det anropande systemet genom en **separat betrodd nyckelring**. Ingen manifestinbäddad nyckel får bli betrodd.
- Okända JSON-fält, dubblettnycklar, fel algoritm, ogiltig Base64/signatur, okänd signerare och privilegierade manifest-/kommandofält avvisas.
- Resultat även vid korrekt signatur: `authorizes_mutation=False`, `requires_human_approval=True`. Ingen deployment-/rollbackfunktion finns.
- Ventuno-isolerad kod- och pytest-körning: [38560174023](https://github.com/Harrokk/Myai/actions/runs/38560174023), **1721 passed, 8 skipped**.
- Hostad Linux med `cryptography==45.0.7` installerad endast i temporär venv: [38560174116](https://github.com/Harrokk/Myai/actions/runs/38560174116), **33 passed**, inklusive verklig Ed25519-signering, fel signerare, modifierad data och signerat men ogiltigt manifest.
- Två kryptografiberoende testfall hoppas över i Ventuno-miljön där kryptografibiblioteket inte finns. Det är avsiktligt fail-closed och installerar inga nya beroenden i produktion.

## PR #145 — motpartsidentitet via Linux-kärnan
- [PR #145](https://github.com/Harrokk/Myai/pull/145), gren `dev/offline-unix-peer-identity-20261014`, baseras på #144.
- `core/selfdev_peer_identity.py` accepterar endast ett **redan anslutet** AF_UNIX/SOCK_STREAM-socketobjekt och läser `SO_PEERCRED` via kernel-socket API. Inget socket-serverlyssnande, bind/connect eller nätverkskommunikation.
- Betrodd runtime-UID-mängd och separat updater-UID läggs in från out-of-band-kodkonfiguration, inte via användarinmatning i IPC-meddelandet. Root/updater får inte bli runtime-identiteter.
- En peer-UID-match tillåter *enbart preview-identitetskontroll*, aldrig kodmutation.
- Tester med verkliga temporära Unix-socketpairs testar PID/UID/GID, förfalskad JSON-identitet, fel UID, trasig policy, avstängda sockets, IPv4-nekan och behörighetsgränser.
- Full Ventuno-isolerad körning: [38560493529](https://github.com/Harrokk/Myai/actions/runs/38560493529), **1736 passed, 8 skipped**, statisk audit PASS utan blockerare.
- `SO_PEERCRED` gäller credentials vid anslutningstillfället; en framtida riktig server måste autentisera *nyligen accepterade* klientanslutningar, inte lita på ett socketpair skapat före setuid/fork.

## PR #146 — komposition och strikt meddelanderam
- [PR #146](https://github.com/Harrokk/Myai/pull/146), gren `dev/offline-inspection-pipeline-20261014`, baseras på #145.
- `core/selfdev_offline_preview_pipeline.py` validerar exakt en 4-byte big-endian längdram högst 40 KiB. Förhandsgranskning prövar i ordning: kernel UID -> frame -> betrodd Ed25519-signatur -> signerad SHA-256 jämförd mot in-memory bytes -> preview-only SQLite deduplicering.
- En dålig UID, signatur, JSON-ram eller filhash får inte skapa ny SQLite-ledger. Positivt resultat `recorded_for_inspection` är aldrig ett installationsgodkännande.
- Ingen live socket server, installerare, git fetch, kodexekverare, service restart, återställare eller systemfilskrivning är kopplad till flödet.
- Ventuno ARM64 isolerad pytest: [38561167248](https://github.com/Harrokk/Myai/actions/runs/38561167248), **1746 passed, 11 skipped**. Extra tre signatur-/integrationsfall körs på hosted CI.
- GitHub-hostad Linux med kryptografibiblioteket i temporär venv: [38561246331](https://github.com/Harrokk/Myai/actions/runs/38561246331), **61 passed**. Utför verklig Ed25519, Unix kernel peer och replay-flöde med temporära socketpairs/SQLite.
- Den återstående körningen efter workflow- och checkpoint-commit måste kontrolleras separat; följ CI per branch.

## Kvarvarande ej verifierade blockerare och risker
1. Protokollet är **ingen skarp autentiserad IPC-tjänst**. Inga server- eller klientloopar, socket-path-behörigheter, timeout- och fragmenteringshantering, throttling eller motpartsgodkännanden finns.
2. Betrodda nycklar och UID-listor kommer från separat, hypotetisk konfiguration. Ingen signerad release från en verklig betrodd distributionskedja har verifierats. Nyckelrotation och återkallelser saknas.
3. En positiv signatur och korrekt filhash bevisar inte att koden är säker, att en specifik människa har godkänt driftsättning eller att kodpaketet ska användas i produktion. Vidare privileged human-approval-ledger och staging krävs.
4. SQLite-preview-ledgern använder temporära testdatabaser. Den är inte en auktoriserad uppdateringsjournal; dess skydd för same-UID angripare är otillräckligt före verklig OS-identitetsseparation.
5. Samma Linux-UID som kan läsa HMAC-nyckeln kan fortfarande förfalska vissa nuvarande selfdev-journaldata; den experimentella UID-containern från [PR #143](https://github.com/Harrokk/Myai/pull/143) visade endast möjlig privilege-matris, inte en migrerad VENTUNO-installation.
6. De sex optional ONNX/NumPy ARM-skipparna verifierades tidigare separat via hosted x86 (22 passed): https://github.com/Harrokk/Myai/actions/runs/38520039444.
7. Verklig eMMC power-cut, produktionsljud/mikrofon, kamera, Bluetooth, NPU/STM32, tjänstomstart samt Windows Arduino App Lab-terminal är utanför denna arbetsomgång.
8. Historiskt cachade känsliga objekt i GitHub måste fortfarande verifieras rensade av Support enligt blockeraren [PR #110](https://github.com/Harrokk/Myai/pull/110). Ingen main merge före det.
9. Full repo static audit har en befintlig manuell `exec`-flagga för en testhjälpfunktion. Den ska inte tystas utan separat granskning.
10. Alla PRs #112–#146 i den aktuella utvecklingskedjan är i utkast eller alternativ, inte mergade. Aktiva MyAI/GenieX på Ventuno har inte ändrats. Automatisk selfdev-promotion förblir avstängd.

## Fortsättningspunkt (kan göras utan fysisk åtkomst)
- Utforma en **helt offline** och avsiktligt icke-privilegierad testtransport med begränsade läsningar, timeouts, disconnects och exact-frame-parser på temporära Unix-socketpairs; ingen server får bindas till produktionssökvägar.
- Separat granskning av signerad release-försörjningskedja och nyckelprovisionering innan en faktisk updater daemon designas.
- Möjliggör host-only Ed25519 integration i CI på varje relevanta huvudgren utan att lägga till kryptografiberoenden i den aktiva VENTUNO-installationen.
- Om något ska kopplas till riktiga programkomponenter senare krävs uttrycklig produktionstest- och migrationsauktorisation.
