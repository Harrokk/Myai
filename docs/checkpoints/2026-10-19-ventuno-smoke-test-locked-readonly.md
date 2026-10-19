# MyAI – låst första VENTUNO smoke-testversion och skrivskyddad förkontroll

**Låst kandidat:** `d28165c1cad81f8b4308ac7355a3fdfd81334986` (DRAFT PR #349), **2026-10-19**.

Denna SHA är ett **orörligt innehålls-ID** för testkoden, inte en release, merge eller påstådd installation på VENTUNO. DRAFT-PR #349 är fortfarande omnergad. Den fullständiga GitHub-hostade ARM64-sviten kördes på exakt SHA i https://github.com/Harrokk/Myai/actions/runs/39190171714 och passerade 4247 tester med 7 överhoppade. Fyr-UID-testet passerade på https://github.com/Harrokk/Myai/actions/runs/39190171681. Dessa körningar **innehåller inga färska fysiska mätningar från VENTUNO**.

**Inga tidigare DRAFT-förändringar får automatiskt installeras i aktiv `/home/arduino/MyAI`.**

## Användarens aktuella tillstånd

Användaren har uttryckligen begärt **en låst testversion och en färsk skrivskyddad kontroll på VENTUNO**. Det är tillstånd för *metadata-inspektion utan ingrepp*, inte nytt tillstånd att spela in mikrofon, spela upp ljud, öppna NPU/FastRPC, stoppa eller starta tjänster, ändra rättigheter, köra `scripts/smoke_test.py` eller installera/merga kod.

## Körmetod

`.github/workflows/ventuno-locked-smoke-readonly-preflight.yml` är ett explicit begränsat Github Actions-test med en enda jobbrunner `[self-hosted, Linux, ARM64, ventuno-q]`. På den fysiska enheten får den:
1. verifiera att användaren **inte** är root och att maskinen är Linux ARM64;
2. hämta **exakt test-SHA** till en **ny tillfällig privat scratch-katalog**, inte den befintliga MyAI-installationen. Inga branch HEAD eller opinnade versioner accepteras;
3. köra `python -B -m scripts.ventuno_physical_pilot_gate --expected-sha <SHA> --source-root . --board-readonly`, vars befintliga implementation bara läser profil, `/proc`, USB-metadata och `systemctl is-active`;
4. köra `python -B -m scripts.ventuno_usb_audio_inventory` som **inte** öppnar /dev-ljud;
5. köra `python -B -m scripts.ventuno_runner_uid_acl_preflight --local-readonly` för begränsade lokala metadata om systemd-/konto-/DAC-kandidater och skriva endast den sanerade rapporten;
6. radera endast den temporära scratch-katalog som jobbet själv skapat.

**Ingen root-/sudo-körning, ingen nyckel, ingen konfigurationsändring, ingen installation, ingen mikrofon, ingen högtalare, ingen LLM/NPU-inferens och ingen `systemctl start/stop/restart`.** Kortets självhostade runner har historiskt körts som `arduino`, vilket är en kvarstående produktionsrisk; ett read-only jobb är **inte** bevis på faktisk UID-/ACL-isolering.

Ingen automatisk pipeline från DRAFT-PR-merge till fysisk installation skapas. Den låsta SHA:n har en egen, separat granskningsgren `dev/ventuno-smoke-locked-readonly-preflight-20261019`. Den grenens workflow-instrumentering kommer att ha en **annan** commit-SHA; jobben kontrollerar alltid testkodens *ursprungliga* låsta SHA, inte instrumentationens HEAD.

## Stoppa på NO-GO

Ett hostat Actions-jobb med grönt resultat betyder **bara att skrivskyddad diagnostik kördes**. Rapporten måste läsas separat:
- exakt SHA och ren checkout;
- aktiv produktionsprofil med `voice.enabled`, `voice.tts_enabled`, `voice.handsfree_enabled` och övriga skrivfunktioner bokstavligen av;
- ARM64 och båda förväntade systemd-tjänster aktiva;
- USB capture + playback på åtkomligt ALSA par 1:0;
- minst 8 GiB ledigt RAM och 3 GiB tillfälligt lagringsutrymme;
- inga öppnade mikrofoner/högtalare eller laddade modeller i förkontrollen;
- lokala runner-konton och ACL är **metadataindikationer**, inte automatik.
- giltiga säkerhetsflaggor i utdata, inga oväntade loggar med integritetskänsligt innehåll.

Om runnern är offline, hänger i kö, blir nekad eller inte finns kvar får vi **inte** påstå att VENTUNO kontrollerats. Stoppa och använd fysisk terminal vid senare uttryckligt tillfälle. Om något objekt rapporterar NO-GO: **inget aktivt ljudtest** innan orsaken är känd.

## Nästa steg efter faktisk färsk grön metadata

1. Gör en kort fysisk genomgång med användaren vid kortet så att USB-mikrofon och högtalare, säker stop-mekanism och fungerande återställning går att kontrollera.
2. Be uttryckligen om ett **nytt engångsgodkännande** för inspelning/uppspelning. Ett skrivskyddat metadata-PASS ger inget sådant tillstånd.
3. Utför en kontrollerad och stoppbar enkel ljudfras → Whisper STT → lokal LLM → TTS. Stoppa efter första avvikelse. Ny inspelning kräver nytt tillstånd.
4. NPU/HTP-stresstest, långtidstest, strömavbrott och automatisk koduppdatering är **separata senare tester** och är fortfarande NO-GO.

Ingen ändring på `main`, ingen faktisk VENTUNO-produktionstjänst ändras och testet ska aldrig betraktas som deployment.
