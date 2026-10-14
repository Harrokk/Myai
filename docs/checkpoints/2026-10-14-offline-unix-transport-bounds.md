# MyAI checkpoint – tidsbegränsad och exakt Unix-preview-transport

**Datum:** 2026-10-14
**Aktuell utvecklingsgren:** `dev/offline-unix-bounded-transport-20261014`
**Draft PR:** [#147](https://github.com/Harrokk/Myai/pull/147), byggd ovanpå [#146](https://github.com/Harrokk/Myai/pull/146).
**Release-status:** INTE INSTALLERAD. Ingen sammanslagning till `main`, ingen aktiv VENTUNO-kod, tjänst, kamera, mikrofon, Bluetooth-parning, OS-användare, systemd-ändring eller fysisk kontroll ändrad. Automatisk MyAI-selfdev-promotion är fortsatt avstängd.

## Implementerat i denna omgång
- `core/selfdev_offline_preview_transport.py` är en verifierbar läsare för **redan anslutna** Linux AF_UNIX/SOCK_STREAM-sockets; skapar/lyssnar/ansluter inte någon socket själv och skickar ingen data.
- Kontroll av Linux kernel `SO_PEERCRED` och konfigurerad runtime-UID sker *innan* några bytes konsumeras. Betrodd UID-policy ligger i anroparens data, inte i meddelandet.
- Avgränsad transport: läs exakt 4-byte big-endian-längd, begränsa nyttolast till 40 KiB, vänta högst en gemensam monotont beräknad tidsgräns (0–5 sekunder, öppet vid 0), läs med select+MSG_DONTWAIT utan att ändra socketens blocking state.
- Kräver `shutdown(SHUT_WR)` från avsändaren efter **exakt ett** meddelande. Avvisar kort header, kort nyttolast, för tidig EOF, saknad EOF, extra/trailande bytes och ihopklistrade meddelanden; långsam/idle peer misslyckas när den gemensamma tidsgränsen går ut.
- En inspektionsfunktion skickar sedan det färdiglästa signerade bytesmeddelandet vidare till #146:s befintliga **offline** komponenter: kernel peer, Ed25519 med oberoende betrodd publik nyckel, SHA-256 över caller-supplied bytes och en preview-only SQLite replay-ledger.
- Framgångsrik granskningsbegäran bär fortsatt `authorizes_mutation=False` och `requires_human_approval=True`. Ingen promotion/rollback/installerare/användarfilsändring är kopplad.
- `tests/test_selfdev_offline_preview_transport.py` innehåller regressioner för fragmentering från annan tråd, tidiga avbrott, noll/överkantlängder, delayed trailing bytes, concatenated frames, ej half-close/timeout, ogiltiga deadlines, fel motparts-UID, stängda sockets, signerad replay och avbrutet signerat meddelande utan ledger-skrivning.

## Verifiering
- ARM64 full pytest på self-hosted VENTUNO Q-runner, **i temporär separat checkout**: [GitHub run 38562773999](https://github.com/Harrokk/Myai/actions/runs/38562773999), **1770 passed, 13 skipped**, source/privacy static audit **PASS, 0 blocking findings**.
- Linux x86 GitHub-hosted testmiljö, egen isolerad venv med `cryptography==45.0.7` och `pytest==8.3.5`: [GitHub run 38562854151](https://github.com/Harrokk/Myai/actions/runs/38562854151), **87 passed**, inklusive real Ed25519 från temporär nyckel, AF_UNIX/peer-kontroller och integration genom hela offlineflödet.
- Hoppen på ARM64 inkluderar sex befintliga host-only ONNX/NumPy-tester som tidigare testats separat på x86 [22 passed](https://github.com/Harrokk/Myai/actions/runs/38520039444), samt crypto-beroende fall; de körs på hosted Linux i stället.
- Allt körs utan att koppla in den aktiva MyAI, göra fysisk åtkomst, ändra tjänster eller installera kryptografibibliotek i produktion.

## Kvarstående risker och releasegrindar
1. Detta är **inte en verklig IPC-server**, autentiserad socket-path, replay-säker approval-tjänst eller privilegierad updater. En framtida socket-server måste dessutom skydda filrättigheter på socketens sökväg, skapa och acceptera anslutningar säkert, hantera bounded accept queues, timeout på processnivå, throttling, anslutningskvoter, server- och klientlivscykel samt eventuell svarstransport.
2. `SO_PEERCRED` avser identitet vid anslutningstillfället; framtida socketserver måste verifiera en nyss accepterad socket och inte lita på en socketpair upprättad före setuid/fork.
3. Ed25519 public-key-keyringen är fortfarande extern trusted testdata, inte en operativt validerad release-nyckel eller key-rotation; signering av inspektionsmanifest är inte godkännande att installera.
4. Preview-ledgern i denna prototyp är inte ett autentiserat godkännandesystem och dess SQLite-databas finns bara i testkataloger.
5. Filsystemsskydd inom samma UID, nyckelägarskap/privilegieseparerad daemon, end-to-end IPC och verklig release-staging är inte installerade. `flock`/hash/fdatasync kan inte ensamt stoppa hostile same-UID writers.
6. Verklig VENTUNO power-cut/eMMC, audio/mic, kamera, BLE, NPU/STM32 och Windows Arduino App Lab-terminal kvarstår separat som icke genomförda fysiska/funktionella tester.
7. GitHub Support-purge av tidigare cachad känslig historik är fortfarande inte bekräftad; [PR #110](https://github.com/Harrokk/Myai/pull/110) blockerar `main`-merge. Samtliga relevanta kod-PRs är fortfarande utkast.
8. Statisk audit har en redan dokumenterad manuell `exec`-flagga i ett internt testhjälpmedel; ingen tyst överstyrning har gjorts.

## Nästa möjliga steg utan fysisk åtkomst
- Utöka tidsgränsregressioner med separat tidsgräns över många korta fragment (slow-trickle), säker timeout utan receiver socket state-mutation och negativa tester för socket-switch under läsning.
- Skissa en test-only engångs-`accept`-server i en disposable Docker/hosted Linux-environment (ej VENTUNO) där SO_PEERCRED kontrolleras på en nyss accepterad anslutning. Inget service/daemon på aktiv enhet.
- Bygg read-only release supply-chain trust policy (key rotation/revocation + signer provenance) som offline testbart kontrakt innan någon installationskod kan införas.
