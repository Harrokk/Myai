# MyAI checkpoint – HTP-resultatverifiering utan falska NPU-framgångar

Datum: 2026-10-14. Ny DRAFT-utvecklingsgren på PR #168, **ej mergad eller driftsatt**.

## Verifierat före ändringen

- [PR #168 CI #38605571914](https://github.com/Harrokk/Myai/actions/runs/38605571914): **1950 passed, 14 skipped**, static audit PASS, 0 blockerande fynd. Tidigare känd manuell `exec`-granskningsflagga kvarstår i annan testfil.
- [PR #168 verklig VENTUNO metadata #38605494879](https://github.com/Harrokk/Myai/actions/runs/38605494879): efter korrigering väljer den experimentella HTP-koden bara de **tre korrekta**, AArch64 ELF-, `qairt-libs`-ägda värdbiblioteken på /usr/lib. Den tidigare koden valde tre andra inoder. Denna mätning är INTE ett funktionellt HTP-test.
- PR #163 korrigerade också Skel-filvalet. Alla sådana ändringar finns endast i DRAFT-kedjan.
- [CPU-referens PR #153 run #38582751317](https://github.com/Harrokk/Myai/actions/runs/38582751317): den verifierade syntetiska DLC:n och 64-byte UFXP8-input gav på riktig VENTUNO **exakt SHA-256 lika med tidigare x86 QNN CPU**: `9f776aec98d9e12d5a33bb91fadcb8d6560293cc3e0d816445be6e9d05928174`. Detta är CPU-inferens, inte HTP.
- HTP-backendens senaste diagnostiserade försök i PR #154 slutade `backend_initialization_failure`. Ingen verifierad NPU-inferens finns.

## Viktig korrigerad sakuppgift: QAIRT-version

Vår DLC-fixtur skapades med QAIRT 2.45, medan installerat system är QAIRT 2.46. **Detta är inte ett bevisat inkompatibilitetsfel.**

Qualcomm AI Hub beskriver explicit att QNN DLC och kontextbinärer är kompatibla med QAIRT-versionen där de byggdes **och nyare versioner**:
https://workbench.aihub.qualcomm.com/docs/hub/api.html

Qualcomm AI Hub beskriver också att DLC-filer är backend-agnostiska i formatet, men att HTP ändå kräver en särskild SoC-anpassad *prepare*-fas. En fungerande CPU-DLC är alltså inte bevis för att HTP stöder grafens alla operatorer eller processdomän:
https://workbench.aihub.qualcomm.com/docs/hub/faq.html

LiteRT beskriver separat `qnn-net-run --dlc_path` (HTP-prepare online) och `--retrieve_context` (förkompilerad binär) samt det verkliga syftet med `libQnnModelDlc.so`:
https://github.com/google-ai-edge/LiteRT/blob/main/litert/vendors/qualcomm/doc/LITERT_QNN_NATIVE_RUN.md

## Upptäckt konkret verifieringsfel

Tidigare `scripts/ventuno_tiny_qnn_htp_once.py` satte:
`status="tiny_qnn_htp_native_inference_succeeded"` och `htp_inference_verified=true` så snart QNN CLI returnerade exit 0 och en valfri 64-byte råfil innehöll minst en icke-nollbyte.

Detta är för svagt: data kan vara felaktiga, komma från annan graf eller beräknas med CPU-fallback. **Även en exakt korrekt utdatafil bevisar inte att något HTP-operatorsteg kördes på acceleratorn.**

## Ändringen

- `scripts/ventuno_qnn_native_result_attestation.py` läser endast en vanlig, ej symlinkad 64-byte råfil i privat `results/Result_0` med katalogbudget. Kräver exakt en råfil, kontrollerar storlek och skiljer nollresultat från SHA-256-jämförelse med redan verifierad CPU-referens.
- Utåt rapporteras enbart kategorier och booleska utfall. Inga utdata, hashar från verkliga körningar, filvägar eller hemliga värden exporteras.
- Exakt SHA-match ges status `cpu_reference_digest_match_but_placement_unverified`. Annan utdata ger `nonzero_output_differs_from_cpu_reference` (inte automatiskt en dålig HTP-graf, eftersom backend-numerik kan skilja sig). Detta är en **sträng jämförelse**, inte en fullständig numerisk toleransoracle.
- `scripts/ventuno_tiny_qnn_htp_once.py` använder nu jämförelsen efter framgångsrik QNN CLI-retur, men lämnar alltid `htp_inference_verified=false` och `htp_operator_placement_verified=false`. Ett nytt HTP-test kräver separat, kvalitetssäkrad operator-placement/profilering innan sådan framgång får markeras.
- 11 syntetiska regressionstester täcker falska positiva resultat, referenshash-konsistens, exakta matchningar, nollfil, fel filstorlek, dubbla utdata, symlänkar, katalogbudget och att HTP-flaggan inte sätts.
- Inget av dessa tester kör QNN eller öppnar NPU.

## Stoppgränser

**Ingen ny HTP-körning godkänns**, ingen workflow som exekverar QNN återaktiveras, inga live-tjänster ändras, ingen apt/udev/ACL/gruppändring, inga USB-mikrofon- eller kameratester, ingen merge eller deployment. QAIRT 2.45→2.46 ska inte gissas vara felets grundorsak; nästa sakliga fråga är en vendorstödd, separat HTP-kontext-/operator-testplan för V75, helst först från verifierat QAIRT-verktyg utanför Ventuno.

Historisk GitHub Support purge [PR #110](https://github.com/Harrokk/Myai/pull/110) är fortfarande separat releaseblockerare.
