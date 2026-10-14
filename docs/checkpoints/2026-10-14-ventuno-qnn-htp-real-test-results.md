# MyAI checkpoint — verklig VENTUNO NPU-väg: kontrollerad QAIRT/HTP-provning

**Datum:** 2026-10-14
**Arbetsgren:** `dev/ventuno-qnn-tiny-htp-feasibility-20261014`
**Nya utkast:** [PR #151](https://github.com/Harrokk/Myai/pull/151), [PR #152](https://github.com/Harrokk/Myai/pull/152).
**Ingen driftsättning:** Ingen merge, ingen serviceändring/omstart, ingen ändring av MyAI/GenieX produktionskataloger, ingen mikrofoninspelning, inget USB-ljudtest, inget sudo. USB-ljudkortet är medvetet **inte inkopplat**, och allt ljudarbete väntar tills användaren ansluter det.

## Verkliga runtime-fynd via self-hosted VENTUNO ARM64

1. Befintligt GenieX/MyAI är aktivt och `127.0.0.1:18181/v1/models` exponerar förväntad Qualcomm Qwen W4A16. Men read-only GenieX PID/process-map/FD-kontroll fann **ingen** för tillfället mappad `libQnnHtp.so` och ingen öppen `/dev/fastrpc-cdsp-secure`. En möjlig on-demand/lazy loading är **inte verifierad**.
2. [Live-backend-gate run 38572529470](https://github.com/Harrokk/Myai/actions/runs/38572529470) returnerade `no_go_backend_unverified`; **ingen** syntetisk HTTP POST/inferens gjordes i GenieX.
3. [Gate diagnostics 38573043720](https://github.com/Harrokk/Myai/actions/runs/38573043720) bekräftade `systemd_geniex=active`, `systemd_myai=active`, modell-API aktiv, minne >3 GiB och läsbara processmappningar, men fortsatt ingen samtidig HTP/FastRPC-evidens.

## Oberoende litet syntetiskt QNN-projekt

4. `fixtures/qairt_245/tiny_qdq_conv.dlc.b64`: SHA256-verifierad **16 004 byte** DLC. Exakta **64 byte** UFXP8-indata är deterministiska. Den lilla modellen har tidigare matchat ONNX-referens numeriskt via riktiga `qnn-net-run` + `libQnnCpu.so` på **en separat disposable x86-host**, [run 38230420369](https://github.com/Harrokk/Myai/actions/runs/38230420369). CPU-paritet bevisar inte HTP-funktion.
5. [Tiny device preflight 38574275599](https://github.com/Harrokk/Myai/actions/runs/38574275599): på riktiga VENTUNO finns `qnn-net-run`, context-binary-generator, QNN-verktyg, `libQnnHtp.so`, `libQnnModelDlc.so`, V75 stub och verifierad DLC. SDK example scan nådde resursgräns, så inventeringen är inte fullständig.
6. [Första enda tiny HTP-försöket 38575357038](https://github.com/Harrokk/Myai/actions/runs/38575357038): explicit godkänt i engångsworkflow, >8 GiB ledigt, inget pågående FastRPC-anrop i GenieX, 16 kB DLC + 64 byte input verificerade. `qnn-net-run` med HTP backend gav **nonzero efter 0,039 s**, ingen verifierad native output eller NPU-inferens.
7. [Skrivskyddad ELF/DSP-diagnostik 38576082239](https://github.com/Harrokk/Myai/actions/runs/38576082239): `libQnnHtp.so`, `libQnnHtpV75Stub.so` och `libQnnModelDlc.so` är verkliga ARM64 ELF-bibliotek; V75 DSP skeleton hittas. `ADSP_LIBRARY_PATH` saknas i GitHub-runnerns miljö. Vendor guidance kräver på flera Qualcomm Linux-plattformar att den pekar mot DSP skeleton-katalog; detta var en **möjlig** förklaring till startup-fel, inte ett bevis på grundorsaken.
8. [Andra/sista tiny HTP-försöket 38576819908](https://github.com/Harrokk/Myai/actions/runs/38576819908) med explicit korrekt V75 DSP-katalog i child `ADSP_LIBRARY_PATH`: **nonzero efter 0,044 s**, ingen native output eller HTP-inferens. Detta bekräftar att saknad variabel **inte ensamt** förklarade felet.
9. Ingen rå QNN stderr/stdout publicerades eller sparades i GitHub. Endast begränsade statusvärden. **Gör inga fler inferensförsök med gissade inställningar.**

## Test och integritet

- `scripts/ventuno_live_qairt_synthetic_once.py` kräver positiv aktiv processbevisning och explicit opt-in före ens en syntetisk HTTP-fråga. I realt test blev det NO-GO utan HTTP POST.
- `scripts/ventuno_tiny_qnn_htp_once.py` begränsar direkt QNN-experiment till en enda liten DLC, max 30 sekunder, 4 GiB virtuell adressrymd, 25 CPU-sekunder och max 2 MiB per utfil i privat `RUNNER_TEMP`. Två separat explicit avgränsade workflows körde de två dokumenterade försöken, utan retry-loop.
- QNN-experimenten skapade **inte** någon ytterligare stor LLM/GenieX-service och ändrade inte aktiv källkod. Fysisk NPU-mätning är fortsatt **inte lyckad/verifierad**.
- Full Ventuno ARM64 regression: [run 38576701229](https://github.com/Harrokk/Myai/actions/runs/38576701229), **1817 passed, 14 skipped**, statisk källkods- och sekretessgranskning PASS, 0 blockerande, 1 tidigare dokumenterad manuell testflagga. Senaste checkpoint-commit ska testas separat av CI.
- Alla relevanta PRs fortsatt DRAFT. Känslig äldre GitHub-historik är fortfarande blockerad i [PR #110](https://github.com/Harrokk/Myai/pull/110) tills GitHub Support har bekräftat purge.

## Nästa enda godtagbara NPU-felsökning

1. Bestäm *exakt* varför vendor CLI avbryter under uppstart. Gör detta först med **read-only** `readelf`/biblioteksdependencykontroll eller översyn av installerade QAIRT-funktionsflaggor och konfigurationskontrakt. Ingen blind upprepning av NPU-testet.
2. Om ett verkligt startupfel behöver samlas in: utforma en särskilt granskad engångskörning med temporär, maxbegränsad `stdout/stderr` och **endast en whitelista av QNN-felkategorier** i användarsynlig logg. Nya live-tester måste ske med tydlig risk-/resursgrind.
3. Alternativt gör en kompatibel HTP v75-kontext med Qualcomm-verktyg på **separat host**, kontrollera tensorlayout och körplats först. Testa inte en ny 4B-modell på VENTUNO vid sidan av live GenieX.
4. Fortsätt separata MyAI-funktioner som inte kräver USB-ljudkort; kontakta användaren endast om verklig kabelåtgärd/fysisk risk kräver det.

**Status:** Verklig Qualcomm QAIRT-miljö, SDK och tiny-DLC-inmatning verifierade. Direkt NPU-exekvering kvarstår *inte bekräftad*, eftersom båda begränsade CLI-körningarna avvisades direkt. Påstå aldrig genomförd HTP-inferens från dessa resultat.
