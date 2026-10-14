# MyAI kontrollpunkt – QAIRT 2.46 och HTP-v75, säkra förberedelser på separat x86-värd

Datum: 2026-10-14. Gren: `dev/ventuno-qairt246-host-htp-preflight-20261014`. Allt är **DRAFT**, ej installerat eller sammanslaget.

## Verifierad historik

- [PR #170 / x86-ONNX Actions #38607427173](https://github.com/Harrokk/Myai/actions/runs/38607427173): 7/7 tester godkända. Exakt 608-byte syntetisk ONNX-fixtur verifierad med SHA-256, IR8, opset13, 7 noder (Q/DQ, Conv, Relu), statiska float32-indata/utdata och fast kvantisering. **Ingen QAIRT 2.46 HTP-operatoracceptans** bevisades.
- [PR #170 / full isolerad ARM64 CI #38607629240](https://github.com/Harrokk/Myai/actions/runs/38607629240): 1967 passed, 15 skipped, statisk source/privacy-granskning PASS 0 blockerande fynd. Separat äldre manuell exec-granskningspunkt kvarstår.
- Tidigare på VENTUNO verifierades installeras **QAIRT 2.46**, qcom FastRPC, CDN/CDSP running, giltiga DSP Hexagon V75-Skel och shell, CPU-inferens med exakt referensparitet. PR #163 och #168 har avgränsade ändringar för strikt DSP- och hostlib-val; PR #169 tog bort en falskt positiv NPU-verifieringsregel. **Alla är utkast; NPU/HTP-inferens är fortfarande inte verifierad.**
- Officiell Arduino VENTUNO-dokumentation identifierar processor **QCS8275 (Dragonwing IQ-8275)** och HTP-v75: https://docs.arduino.cc/tutorials/ventuno-q/llama-cpp/
- Qualcomm anger att en HTP-kontext måste byggas för rätt SoC och att man ska kontrollera `soc_model` mot **Supported Snapdragon Devices** för den **exakta SDK-versionen**. Kontextgenereringen använder `qnn-context-binary-generator`, host `libQnnHtp.so`, DLC-laddare `libQnnModelDlc.so`, med backend extensions om konfiguration behövs:
  https://dev.aihub.qualcomm.com/docs/hub/faq.html
  https://docs.qualcomm.com/nav/home/htp_auto_optimization.html?product=924033590759186372
  https://github.com/google-ai-edge/LiteRT/blob/main/litert/vendors/qualcomm/doc/LITERT_QNN_NATIVE_RUN.md
- Qualcomm säger att DLC är kompatibel med producerande och nyare QAIRT-versioner. Det betyder **inte** att en graf garanterat går att HTP-kompilera: https://workbench.aihub.qualcomm.com/docs/hub/api.html

## Ny begränsad preflight

- `scripts/ventuno_qairt246_offhost_htp_preflight.py` vägrar ARM64/VENTUNO. Vid normal CI-körning **finns inget proprietärt QAIRT SDK**, så korrekt status är `no_go_sdk_not_supplied` trots SHA-verifierad syntetisk DLC.
- En **separat redan auktoriserad** lokal SDK-katalog med namn som ser ut som QAIRT `2.46.x[.build]` får läsas **endast som metadata** (katalognamn bevisar aldrig provenance). Fyra exakta filer kan undersökas, under `bin/x86_64-linux-clang` respektive `lib/x86_64-linux-clang`: context generator, HTP backend, DLC-loader och HTP backend extension. Tillåt bara vanliga filer med rimlig storlek och korrekta **x86_64 ELF-header** (högst 64 byte per fil, O_NOFOLLOW, fstat-säkerhet). Inga dynamiska bibliotek laddas, inga SDK-verktyg exekveras.
- Den redan incheckade lilla DLC:n verifieras med sin exakta SHA-256 och filstorlek, men detta är **inte** HTP-kompatibilitetsbevis.
- Om alla syntetiska hostfiler ser giltiga ut returneras ändå endast `no_go_manual_vendor_sdk_and_soc_attestation_required`: SDK:s äkthet och **numeriskt Qualcomm soc_model/soc_id** har **inte** verifierats via VENTUNO/Arduinos och QAIRT-versionens offentliga hårdvarutabelldokumentation. Inga värden gissas; varken `V75` ensamt eller liknande Qualcomm-proxychip räcker.
- Tio syntetiska tester omfattar ARM-avslag, frånvarande SDK, giltig/felaktig host ELF, fel SDK-version, symlänkar, korrupt DLC och avsaknad av falska HTP- eller licens-/vendorproveniensanspråk.
- GitHub Actions-jobbet använder **GitHub-hosted x86/Ubuntu**, exakt SHA och temporär checkout. Det installerar bara **pytest 8.3.5 i en temporär venv på GitHub-host** för regressionstester, men hämtar eller installerar **inte QAIRT eller Qualcomm-komponenter**, och exekverar **inga** HTP-, DSP-, modell- eller firmwarefunktioner och har inga action secrets utöver begränsad token för källkodshämtning.

## Stoppvillkor före någon framtida fysisk NPU-körning

1. En betrodd och licensmässigt godkänd QAIRT **2.46 host SDK** måste kunna verifieras i en separat granskning. Vi har inte gjort detta.
2. Bekräfta **rätt numeriskt soc_model och V75-målfamilj** i den faktiska SDK 2.46-tabellen eller uttrycklig Qualcomm/Arduino-vendorinformation. Ingen gissning från en liknande telefon eller ett proxychip.
3. Värdgenerera och validera förberedd HTP-kontext **endast om separat auktoriserat och med dokumenterade SDK-flaggor**. Det här steget skapar ingen sådan.
4. Faktisk operatöracceptans, processdomän, firmwarekompatibilitet och HTP-placering på NPU kräver ett separat test med resursspärrar, isolering och explicit godkännande. En kontextfil eller SHA-identisk output bevisar inte själv NPU-exekvering.

**Ingen** apt/pip-installation av Qualcomm SDK, ny nätverksnedladdning, production merge/deploy, `sudo`, ACL/udev/gruppändring, symlink- eller firmwareändring, service-omstart, ljud- eller kameraaktivitet eller HTP-modelltest ingår. Historisk GitHub Support-purge [PR #110](https://github.com/Harrokk/Myai/pull/110) förblir separat releaseblockerare.

## Nytt verifierat vägval – exakt Arduino-enhet i Qualcomm AI Hub

Officiell [Arduino-guide för Qualcomm AI Hub på VENTUNO Q](https://docs.arduino.cc/tutorials/ventuno-q/getting-started-qc-ai-hub/) anger **`Arduino VENTUNO Q` (Ubuntu 24.04)** som den riktiga molnmålenheten, medan **`QCS8275 (Proxy)` (Android 14)** bara är en fallback. Därmed behöver man **inte manuellt gissa ett numeriskt `soc_id` om man väljer den dokumenterade QAI Hub cloud-rutten med namngiven målenhet**. Detta ändrar inte de strikta kraven för en *lokal* vendor-SDK/context-generator som fortfarande behöver rätt konfiguration.

[Qualcomms officiella API-dokumentation](https://workbench.aihub.qualcomm.com/docs/hub/api.html) anger `--qairt_version 2.46`-liknande **major.minor**-syntax och att man måste verifiera faktiskt erbjudna versioner genom `get_frameworks()`. **Det är ännu inte verifierat att QAI Hub i dag erbjuder exakt 2.46 för vår målenhet och kompileringstyp.** Qualcomms dokumenterade [compile-and-link-API](https://workbench.aihub.qualcomm.com/docs/hub/generated/qai_hub.submit_compile_and_link_jobs.html) kan skapa en SoC-specifik QNN-kontext; `qnn_dlc` är däremot hårdvaruagnostisk och **inte** en förkompilerad HTP-kontext. Dessa artefakter får inte blandas ihop.

Publika AI Hub-profiljobb från **Arduino VENTUNO Q** finns med faktisk rapporterad NPU-beräkning (exempel: [public job med QAIRT 2.45](https://aihub.qualcomm.com/jobs/j5671y4vp) och [public job med QAIRT 2.50](https://aihub.qualcomm.com/jobs/jgnzx03mg)). Det är **andras modeller i Qualcomms tjänst**, inte vår tiny-QDQ-graf, och bevisar varken exakt QAIRT 2.46, användarkontots åtkomst, vår HTP-operatoracceptans eller lokal drift i MyAI.

`scripts/ventuno_qai_hub_offhost_target_policy.py` lägger därför till ett **alternativt, helt offline** beslutsflöde:
- Kräver exakt `Arduino VENTUNO Q`, nekar Android-proxyn och närliggande namn.
- Skiljer `qnn_dlc` från `qnn_context` (Cloud compile/link) samt den exakt kontrollerade ONNX-fixturens modellmetadata.
- Kräver explicit verifierad 2.46-tillgänglighet i *live* AI Hub-katalog, behörig autentisering och **separat uttryckligt samtycke till modelluppladdning och jobbinlämning**. Alla uppgifter är för närvarande obekräftade. En eventuell framtida metod ska granska sekretess och tredjepartsöverföring innan något görs.
- Även om någon skulle markera alla dessa villkor som sanna ger koden endast `manual_service_and_model_review_required_no_submission`. **Ingen token läses, API anropas, modell skickas eller kompilering startas.**
- Tio nya syntetiska tester verifierar exaktnamn, OS-/proxy-skillnad, runtime-artefakttyp, version/behörighetskontroller och fail-closed-regler.

**Förväntat verkligt beslut nu:** `no_go_246_not_confirmed_in_live_cloud_catalog` för exakt Arduino-mål, medan den fristående lokala SDK-vägen fortsatt ger `no_go_sdk_not_supplied`. Inget av detta är HTP-fel på VENTUNO.

### Uppdaterad nästa prioritet

Verifiera den officiellt erbjudna QAIRT-versionen och exakt kompileringsstöd för enheten **via betrodda Qualcomm-dokument/API med behörig användare**. Om exakt 2.46 saknas i molntjänsten, gör ingen automatisk uppgradering av kortets befintliga 2.46-runtime. Ingen molnuppladdning, modellkörning eller produktionsändring får ske utan separat godkännande.

## Offentliga Qualcomm-jobb, jämförda med installerad runtime (2026-10-14)

Publicerade riktiga jobb på **Arduino VENTUNO Q, Ubuntu 24.04** bekräftar att Qualcomms namngivna mål kan rapportera NPU-op-placering, men endast för andra modeller och de versioner som de specifika jobben visar:

- [Qualcomm AI Hub, densenet121, 8 augusti 2026](https://aihub.qualcomm.com/jobs/jgllw4omg): QAIRT **2.45.0.260326154327**, NPU **374** operatörer.
- [Qualcomm AI Hub, regnet_y_800mf, 20 september 2026](https://aihub.qualcomm.com/jobs/jgk2dn0vg): QAIRT **2.50.0.260828221209**, NPU **195** operatörer.
- [Qualcomm AI Hub, sam3_vision_backbone, 3 oktober 2026](https://aihub.qualcomm.com/jobs/jpyo00j05): QAIRT **2.50.0.260828221209**, NPU **1845** operatörer.
- [Arduino VENTUNO Q Qualcomm AI Hub-guide](https://docs.arduino.cc/tutorials/ventuno-q/getting-started-qc-ai-hub/): använder direkt `Arduino VENTUNO Q` (Ubuntu 24.04) och förklarar att `QCS8275 (Proxy)` är Android-proxy.
- [Qualcomm Working with Frameworks](https://workbench.aihub.qualcomm.com/docs/hub/frameworks.html): exakt tillgängliga QAIRT-versioner och deras API-värden ska inhämtas via `get_frameworks()` / `qai-hub list-frameworks`, med en autentiserad och godkänd klient.

**Tolkning:** publik dokumentation och jobb visar att riktiga VENTUNO Q kan köra NPU-modeller på Qualcomms molnplattform, men detta **verifierar inte** att AI Hub erbjuder exakt `2.46` för vår graf, att användaren har tillgång till motsvarande compile/link-tjänst eller att en QAIRT 2.50-kontext skulle vara kompatibel med VENTUNO-enhetens installerade QAIRT **2.46**. Inga sådana antaganden ska göras; med begränsad offentlig information kvarstår `no_go_246_not_confirmed_in_live_cloud_catalog` enligt policyn.

**Ingen** Qualcomm-identitet, API-token, privat modell, delad data eller HTP-jobb användes för dessa observationer.
