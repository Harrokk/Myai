# MyAI – HTP-hostbibliotek och QAIRT-proveniens på Ventuno Q

Datum: 2026-10-14. Utvecklingsgren: dev/ventuno-htp-hostlib-qairstack-parity-20261014. DRAFT, ingen merge eller produktionsändring.

## Varför denna kontroll har större värde än fler filinventeringar

- [PR #166 CI #38603731208](https://github.com/Harrokk/Myai/actions/runs/38603731208): **1940 passed, 14 skipped**, statisk integritetsgranskning PASS med 0 blockerande fynd.
- [PR #166 faktiskt metadataresultat #38603500833](https://github.com/Harrokk/Myai/actions/runs/38603500833): CDSP körs; en firmwarefilskandidat finns men saknar dpkg-ägarträff; FastRPC unsigned shell ägs av ett annat paket än den snäva allowlisten. Detta är INTE ett verifierat fel eller firmware mismatch. Metadatakedjan har inget säkert versionskriterium för firmware.
- I `scripts/qairt_245_dlc_static_audit.py` ligger den exakt verifierade 16 004-byte syntetiska DLC-fixturen från **QAIRT 2.45.0.260326**, medan [PR #159 på verklig VENTUNO](https://github.com/Harrokk/Myai/actions/runs/38594879492) verifierade `qairt-libs` och `qairt-dsp-binaries` **2.46.0-0ubuntu1~bpo24.04.1**.
- CPU QNN lyckades på samma DLC i [PR #153 run #38582751317](https://github.com/Harrokk/Myai/actions/runs/38582751317), men HTP-initiering gav kategorin `backend_initialization_failure` i PR #154. CPU-kompatibilitet bevisar inte HTP-grafstöd, op-placement, DSP-PD eller ABI-versionsmatchning.
- [PR #162 real read-only Skel selector #38598267753](https://github.com/Harrokk/Myai/actions/runs/38598267753) hittade att den tidigare **DSP-Skel-väljaren** valde en annan fil än installerat paketerad Skel. PR #163 korrigerade valet genom fail-closed, men är fortfarande utkast.
- QNN-hostbiblioteken väljs i `_find_libraries()` med en bred, begränsad katalogsökning. Denna sökning behöver separat jämföras mot `/usr/lib`-filerna; en tidigare verifierad Skel säger inget om HTP Host-lib-valet.

## Officiella QNN-underlag

- Google LiteRT:s Qualcomm-instruktioner visar att online-DLC-vägen använder `libQnnModelDlc.so` och `--dlc_path`, medan på förhand HTP-kompilerad binär använder `--retrieve_context`. De är **olika valideringsvägar**. Underlag: https://github.com/google-ai-edge/LiteRT/blob/main/litert/vendors/qualcomm/doc/LITERT_QNN_NATIVE_RUN.md
- Qualcomm AI Hub FAQ kopplar vanliga HTP-initieringsproblem och error `1008` till frånvaro eller oförmåga att hitta rätt DSP-Skel/arkitektur och dokumenterar `ADSP_LIBRARY_PATH`. **MyAI har inte verifierat error code 1008**, enbart kategorin backendinitieringsfel: https://workbench.aihub.qualcomm.com/docs/hub/faq.html

## Ny avgränsad revision

- `scripts/ventuno_htp_hostlib_qairstack_parity_readonly.py` anropar **endast den tidigare QNN-testkodens filväljare**, identifierar befintlig ELF-filmetadata för de tre fasta namnen `libQnnHtp.so`, `libQnnHtpV75Stub.so` och `libQnnModelDlc.so`, jämför internt `st_dev/st_ino` mot motsvarande fasta `/usr/lib`-filer. Varken inodnummer eller paths exporteras.
- Läs `dpkg-query -W` för exakt två tillåtna paket `qairt-libs` och `qairt-dsp-binaries` via befintlig validerad datarutin, och verifiera integriteten hos den egna syntetiska DLC-fixturen. Endast sanerade versionssträngar och booleska utfall returneras.
- Versionsskillnad `2.45` → `2.46` rapporteras explicit men `cross_minor_htp_compatibility_proven=false`. Det betyder varken att modellen är inkompatibel eller att HTP-initieringen misslyckades *på grund av* DLC-versionen.
- Sju syntetiska regressionstester skiljer samma filidentitet från identiska kopior med annan inod, och säkerställer att inga privata sökvägar eller inod-ID:n publiceras.
- Branch/path-begränsat Actions-workflow i temporärt exakt commit-checkout och samma runner. Ingen QNN, NPU-körning, firmwareläsning, modellinläsning eller tjänsteändring.

## Stoppbeslut

Resultatet från denna kontroll avgör om en separat **fail-closed hostbiblioteksfix** krävs, liknande Skel-fixen, eller om hostvalet redan är korrekt och HTP-felet kvarstår vid processdomän, backendkonfiguration eller modellkompatibilitet. Inget nytt HTP-försök mot Ventuno är godkänt av enbart dessa metadata. Produktionen, USB-ljud, kamera och GenieX lämnas orörda. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk secret purge är fortfarande en separat blockerare.
