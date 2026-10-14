# MyAI checkpoint – syntetisk Q/DQ-modell verifierad på fristående x86-host

Datum: 2026-10-14. Utvecklingsgren: dev/ventuno-htp-offhost-qdq-contract-20261014. **DRAFT; ingen merge eller installation på VENTUNO**.

## Verifierat sedan tidigare

- PR #169, [full ARM64 CI #38606469832](https://github.com/Harrokk/Myai/actions/runs/38606469832): **1961 passed, 14 skipped**, statisk source/privacy-audit PASS och 0 blockerande fynd. En äldre separat manuell `exec`-granskningsflagga kvarstår.
- PR #169 ändrade HTP-diagnostiken så att **godtyckligt icke-noll 64-byte-utdata inte längre kan räknas som verifierad NPU-inferens**. Även exakt SHA-match mot den verkligt verifierade x86/VENTUNO QNN CPU-referensen bevisar inte HTP-operatorplacering.
- QAIRT-värdpaket och DSP-Skel hade korrekta filer på VENTUNO enligt de tidigare metadatajobben. DLC:n är SHA-verifierad och genererad med QAIRT 2.45, installerad runtime är 2.46. Qualcomm dokumenterar generellt framåtkompatibla DLC:er, så versionsskillnaden är inte i sig felbevis. Däremot är V75-specifikt HTP-operatorstöd och processdomän fortfarande otestade.

## Off-device-kontroll på riktig GitHub-host

[Hosted x86 Actions #38607427173](https://github.com/Harrokk/Myai/actions/runs/38607427173) – **SUCCESS, 7/7 tests passed**.

Den exakta, deterministiskt återskapade syntetiska ONNX-fixturen hade:
- Exakt filstorlek **608 byte**, SHA-256 verifierad mot det tidigare låsta källmodellvärdet `e347c2197d3006e32eec580c85a6eb2c0cbd460150d4a72ae80e9d78573b94f9`.
- ONNX **IR 8, opset 13** och statiskt in-/utformat `float32[1,1,8,8]`.
- Exakt sju operatörer: **2 QuantizeLinear, 3 DequantizeLinear, 1 Conv, 1 Relu**. Inga dynamiska former. Conv använder 3×3 vikter, symmetric pads (1,1,1,1).
- Förväntad kvantisering: input `x_scale=1/32`, `x_zero=128 (uint8)`; vikt `w_scale=1/64`, `w_zero=0 (int8)`; utdata `y_scale=1/512`, `y_zero=0 (uint8)`. Alla sju initializervärden och tensorformer matchade.
- `onnx.checker.check_model(full_check=True)` lyckades och den rena strukturkontrollen godkände exakt topologi och SHA.
- Utförd **enbart på GitHub-hostad x86 Ubuntu-runner** med `onnx==1.17.0` och `pytest==8.3.5`. Inget QAIRT SDK installerades, inget `qnn-context-binary-generator`, `qnn-net-run`, HTP, NPU eller DSP startades, och ingen server hos användaren berördes.

## Exakta begränsningar

**Detta är ett modellkällkods-/ONNX-schemaresultat, inte ett HTP-kompatibilitetscertifikat**. Följande bevis saknas fortfarande:

1. **Verifierad QAIRT 2.46 host SDK** med rätt V75/SoC-specificerad context-generator på fristående x86-värd. Version och binärintegritet måste granskas före körning.
2. Oberoende **HTP operator-stöd** för exakt Q/DQ/Conv/Relu-konfiguration, eller en lyckad förkompilering med Qualcomms verktyg mot korrekt chip/HTP. En DLC som fungerar med QNN CPU är inte tillräckligt bevis.
3. **Signerad/osignerad processdomän, DSP/firmware-kompatibilitet** och eventuell CPU-fallback måste separat verifieras. En korrekt utdatafil räcker inte för att påstå NPU-exekvering.
4. Utvärdering av ett eventuellt värdbyggt HTP-kontextartefakts **signatur, bytes, storlek, SoC-model och ABI** innan någon överföring till VENTUNO ens diskuteras.

Leverantörskällor:
- Qualcomm AI Hub API: https://workbench.aihub.qualcomm.com/docs/hub/api.html
- Qualcomm AI Hub FAQ: https://dev.aihub.qualcomm.com/docs/hub/faq.html
- Googles LiteRT QNN native-guide (DLC online-prepare kontra HTP context offline): https://github.com/google-ai-edge/LiteRT/blob/main/litert/vendors/qualcomm/doc/LITERT_QNN_NATIVE_RUN.md
- Arduino VENTUNO Q QNN/NPU-guide: https://docs.arduino.cc/tutorials/ventuno-q/getting-started-qc-ai-hub/

## Säkerhetsgräns och nästa steg

Denna PR gör **inte** en QNN/HTP-konvertering, skriver ingen firmware eller produktionskonfiguration, installerar inget på VENTUNO och utlöser inget nytt NPU-test. Ett framtida verkligt HTP-försök behöver separat granskning med verklig backend-/operator- och placement-verifiering och uttryckligt godkännande.

Inget sudo, chmod/chown, udev/ACL/gruppändring, uppgradering, processomstart, ljud eller kamera. Alla nya PR:ar förblir utkast. Historisk GitHub Support-purge i [PR #110](https://github.com/Harrokk/Myai/pull/110) är fortsatt separat releaseblockerare.
