# MyAI checkpoint — temporär Unix-accept, långsamma meddelanden, nyckelrotation

**Datum:** 2026-10-14
**Senaste säkra utvecklingsgren:** `dev/offline-preview-key-rotation-20261014`
**Nya draft-PRs:** [#148](https://github.com/Harrokk/Myai/pull/148) och [#149](https://github.com/Harrokk/Myai/pull/149)
**Driftsättning:** NEJ. Ingen merge till main. Ingen installation, tjänstomstart eller fysisk kontroll på den aktiva VENTUNO Q. MyAI/GenieX och deras riktiga filer/nycklar är orörda. Automatisk självuppdatering är avstängd.

## PR #148 – faktisk kernel-UID vid en ny, tillfällig AF_UNIX-anslutning
- Gren `dev/offline-accepted-unix-peer-20261014` utgår från #147.
- `tests/test_selfdev_ephemeral_accept.py` använder **endast pytest-temporära privata socketkataloger** (`0700`) och Unix-socket (`0600`), inga systemtjänster eller produktionssökvägar.
- Barnprocess skapas via fork, ansluter **efter** att testlyssnaren skapats. Den accepterade socketens verkliga SO_PEERCRED PID matchar barnprocessens PID, och kernel UID/GID verifieras.
- Fel runtime UID vägras innan en enda byte konsumeras, även om meddelandet självt hävdar ett annat UID. Testar också tidig frånkoppling, accept-timeout och borttagning av testsocket.
- Fyra extra transporttester provar långsam bytevis sändning som inte får återställa en gemensam deadline, bevarad receiver-blocking/-timeout-konfiguration samt stängd socket under läsning.
- Isolerad VENTUNO ARM64-regressionssvit: [run 38564955264](https://github.com/Harrokk/Myai/actions/runs/38564955264) **1779 passed, 13 skipped**, statisk säkerhetsaudit PASS.
- Hosted Linux-test med testvenv: [run 38564955395](https://github.com/Harrokk/Myai/actions/runs/38564955395) **63 passed**, inklusive accepterad AF_UNIX-postfork-anslutning och slow-trickle.

## PR #149 – en separat signerad previews betrodda nyckelpolicy
- Gren `dev/offline-preview-key-rotation-20261014`, staplad på #148.
- Ren policy-modul `core/selfdev_preview_trust_policy.py`, ingen hemlig nyckellagring eller produktionsintegration.
- Kräv out-of-band betrodd exakt SHA-256-fingerprint per Ed25519-signerare, validera signerar-ID, publika nyckelbytes, ägarskap i policyn (administrativt levererad separat), period med `start <= now < end` och högst 16 poster.
- Dubblett-ID, publik nyckel återanvänd under annat ID, okända/uteslutna pins eller osäkra klock-/statusfält blockeras. `revoked=True` exkluderar alltid signerarens nyckel, även om klockan ändras bakåt.
- Överlappande giltighetsfönster stöder planerad signerarrotation; efter slutdatum blockeras gammal signerare. Positivt resultat kan fortfarande **bara** validera `inspect_candidate`; `authorizes_mutation=False`.
- Tester med äkta Ed25519 från **tillfälliga in-memory-nycklar** på hosted Linux verifierar gammal/ny signerare, återkallelse och förfalskade keypins. Inga nycklar kopieras till VENTUNO.
- Full VENTUNO ARM64-regressionssvit, *inklusive ny CI workflow*: [run 38565813106](https://github.com/Harrokk/Myai/actions/runs/38565813106) **1800 passed, 14 skipped**, source/privacy static audit **PASS, 0 blocking findings**, 1 tidigare dokumenterad manuell flagga (testkodens `exec`).
- Hosted Linux signer-policy med cryptography==45.0.7: [run 38565813254](https://github.com/Harrokk/Myai/actions/runs/38565813254) **55 passed**.
- Under #148/#149 valideras källkodstest enbart i Github-runnerns temporära checkout; inga aktiva MyAI-program/processer konfigureras om.

## Konkreta säkerhetsgränser
1. Testlyssnaren är *inte* en permanent server, updater daemon, tjänst, autentiserad human-approval-ledger eller riktig produktions-IPC. Den skapas bara inom testkatalog och lämnar ingen socket kvar.
2. Samma UID-kod med full åtkomst till både nyckelpolicy och fingerprintpins kan ändra båda. Verklig OS-isolering och verifierad root-of-trust-provisionering saknas ännu.
3. Betrodd monoton klocka över omstarter, out-of-band signatur för administrativ nyckelpolicy, signerad produktionsrelease, key escrow, rotation av riktig hemlig nyckel och persistent signer-revocation är **inte** implementerade.
4. En signerad `inspect_candidate`-request är inte säker kod, inte produktionssamtycke och ger aldrig rätt att installera/återställa/förändra filer.
5. Fysisk power-cut/eMMC-testning, live ljud/USB-mikrofon, BLE, kamera, NPU/STM32, Windows Arduino App Lab invalid IP och installations-/systemd-migration ligger kvar utanför denna icke-fysiska omgång.
6. GitHub Support har inte bekräftat rensning av historiska cachade känsliga objekt; blockeraren [PR #110](https://github.com/Harrokk/Myai/pull/110) är fortsatt inte avslutad. Aktuella PRs fortsätter som *draft*, ingen main-merge.
7. VENTUNO CI skippar valfria host-only ONNX/NumPy och kryptotester där paketen saknas. De relevanta host-only kryptotesterna verifieras av separata GitHub-hostade Linux-körningar. Körningar på självhostad VENTUNO runner är temporär källkodsexekvering, inte fysisk power-loss eller live-systemvalidering.

## Nästa möjliga icke-fysiska steg
- Granska administrationspolicyn för signeringsnycklar med oberoende signerad konfiguration och persistenta anti-rollback-regler. Håll det som en annan *ren* testmodell, inte en faktisk updater.
- Hårdna resursgränser för en möjlig framtida IPC-server via hosted disposable CI: många tomma samtidiga anslutningar, tidsgränser och test-only connection quota, utan produktions-lyssnare.
- Validera PR-stacken och release-migreringsplan i en separat integreringsgranskning. Inga automatiska merger eller uppdateringar av aktiv hårdvara utan godkännande.
