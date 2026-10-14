# MyAI — NPU-prövning via GitHub-runner (14 oktober 2026)

**Beslut om ljud:** USB-ljudkortet är medvetet inte inkopplat på VENTUNO och ska inte felsökas eller testas före anslutning.

## Verklig live-kontroll och varför inferens inte kördes

- GitHub-jobb [38572529470](https://github.com/Harrokk/Myai/actions/runs/38572529470): den begränsade QAIRT-syntetfrågan lämnade status `no_go_backend_unverified`. **Ingen POST-fråga skickades**, ingen modell laddades och inga tjänster ändrades.
- Read-only orsaksdiagnostik [38573043720](https://github.com/Harrokk/Myai/actions/runs/38573043720): `myai-geniex.service` och `myai-ventuno.service` var aktiva; `127.0.0.1:18181/v1/models` rapporterade den förväntade Qualcomm Qwen W4A16-modellen; minnet översteg 3 GiB.
- Däremot saknade den observerade GenieX-processens mappade bibliotek just då `libQnnHtp.so` och dess filbeskrivare saknade `/dev/fastrpc-cdsp-secure`. Processens minnesmappningar var läsbara, så detta är en **faktisk avsaknad av den kräva samtidiga backendevidensen**, inte ett bevis för att en QNN-modell inte kan laddas senare.
- Möjlig lazy loading är en hypotes och har inte verifierats. Att överskrida säkerhetsgrinden för en live-4B-modell utan ytterligare underlag vore ogrundat. Allt skall förbli ostört.

## Tidigare verifierad syntetisk modell

- `fixtures/qairt_245/tiny_qdq_conv.dlc.b64`: SHA256-verifierad 16 004 byte DLC, konverterad med Qualcomm QAIRT 2.45.
- Den syntetiska 8×8-modellen har 64 bytes UFXP8-indata, och CPU-baserad `qnn-net-run`-inferens samt numerisk överensstämmelse med en separat ONNX Runtime-referens verifierades tidigare på en **disposable x86 Linux-värd**, enligt `docs/VENTUNO_QAIRT_PROFILING.md`, [körning 38230420369](https://github.com/Harrokk/Myai/actions/runs/38230420369).
- HTP-v75-kontext, operatorplacering, faktisk NPU-inferens och optrace är **inte** verifierade på VENTUNO.

## Nuvarande arbete

- `scripts/ventuno_tiny_qnn_htp_readiness.py` inspekterar endast verktygs-/SDK-presens, verifierad syntetisk DLC-fingeravtryck i repo och QNN CLI:s dokumenterade flaggor på **riktig ARM64-enhet**. Undersökningen använder inga modell-/personliga data och kör **ingen** inferens, SDK-konvertering eller ny service.
- Fortsatt beslut är NO-GO för en separat HTP-körning tills QNN ModelDlc-backend, HTP-backend, native-input-list, operatorkompatibilitet, minnesbudget, originalkontext och körväg har validerats oberoende.
- Skrivskyddad statuskontroll är inte ett hårdvarufel eller bevis på NPU-avsaknad.

## Drifts- och sekretessgräns

Inget ljud spelas in/spelas upp, inga USB-förbindelser inventeras för felsökning, inga persondata/IP/MAC/SSID/filnamn skrivs till GitHub-logg, inga aktiva MyAI/GenieX-tjänster startas om och inga drivrutiner eller modeller installeras. Alla utkast är omärgade och självuppdateringen är avstängd. Historisk GitHub-purge [PR #110](https://github.com/Harrokk/Myai/pull/110) måste fortfarande hanteras före main-merge.
