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
- GitHub Actions-jobbet använder **GitHub-hosted x86/Ubuntu**, exakt SHA och temporär checkout. Det installerar/downloadar **inte QAIRT eller andra verktyg**, exekverar **inga** HTP-, DSP-, modell- eller firmwarefunktioner och har inga action secrets utöver begränsad token för källkodshämtning.

## Stoppvillkor före någon framtida fysisk NPU-körning

1. En betrodd och licensmässigt godkänd QAIRT **2.46 host SDK** måste kunna verifieras i en separat granskning. Vi har inte gjort detta.
2. Bekräfta **rätt numeriskt soc_model och V75-målfamilj** i den faktiska SDK 2.46-tabellen eller uttrycklig Qualcomm/Arduino-vendorinformation. Ingen gissning från en liknande telefon eller ett proxychip.
3. Värdgenerera och validera förberedd HTP-kontext **endast om separat auktoriserat och med dokumenterade SDK-flaggor**. Det här steget skapar ingen sådan.
4. Faktisk operatöracceptans, processdomän, firmwarekompatibilitet och HTP-placering på NPU kräver ett separat test med resursspärrar, isolering och explicit godkännande. En kontextfil eller SHA-identisk output bevisar inte själv NPU-exekvering.

**Ingen** apt/pip-installation av Qualcomm SDK, ny nätverksnedladdning, production merge/deploy, `sudo`, ACL/udev/gruppändring, symlink- eller firmwareändring, service-omstart, ljud- eller kameraaktivitet eller HTP-modelltest ingår. Historisk GitHub Support-purge [PR #110](https://github.com/Harrokk/Myai/pull/110) förblir separat releaseblockerare.
