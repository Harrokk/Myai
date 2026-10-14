# MyAI – fail-closed-korrigering av V75 Skel-väljaren

Datum: 2026-10-14. Ny isolerad utvecklingsgren efter PR #162. Ingen driftsättning/merge.

## Verifierad orsak till att vi ändrar själva testkoden

- [PR #161, riktig VENTUNO #38597705438](https://github.com/Harrokk/Myai/actions/runs/38597705438): QAIRT 2.46 och qcom-fastrpc1 1.0.15 installerade. Den officiella V75-Skel-målfilen är en **Hexagon ELF** som ägs av `qairt-dsp-binaries`; ingen NPU-inferens utfördes.
- [PR #162, riktig VENTUNO #38598267753](https://github.com/Harrokk/Myai/actions/runs/38598267753): äldre `_find_v75_skel_directory()` fann en annan Skel-kandidat, men vald kandidats dev/inode matchade **inte** den officiellt paketerade Skel-filen. Mätningen bevisar inte att den historiska HTP-körningen använde exakt samma fil eller att mismatchen orsakade dess backendfel. Den motiverar däremot en säkrare väljare.
- Kodgranskning: äldre kataloglista saknade `/usr/lib/dsp/cdsp` och hoppade över symlink (vilket officiell Skel är).

## Ändring

- `scripts/ventuno_tiny_qnn_htp_once.py::_find_v75_skel_directory` är nu **strikt**. Den använder endast `/usr/lib/dsp/cdsp/libQnnHtpV75Skel.so` och returnerar dess katalog för `ADSP_LIBRARY_PATH` bara om den uppslagna målfilen ligger under /usr, är vanlig, har läsbar korrekt **Hexagon ELF-header** och ägs av `qairt-dsp-binaries`.
- Alla andra varianter returnerar **None** och leder till befintlig status `no_go_missing_htp_v75_dsp_skel` innan HTP-anrop. Namnet på denna no-go-status kan tolkas bredare än att filen saknas (även osäker/otillåten fil), men den är säker och befintlig.
- Funktionen använder samma begränsade ELF-/paketkontroll som redan fått godkända isolerade tester i PR #161. En lokal biblioteksfil kan läsas (max 64 bytes); inga device-noder öppnas, och ingen QNN-bibliotekskod körs vid preflight.
- Tre tillagda syntetiska regressionstester visar acceptans av korrekt fil, avslag på fel klass/paket/sökväg och att ingen okänd reservfil väljs.

## Viktiga restriktioner

**Detta är inte ett godkännande att köra HTP igen.** HTP-gaten kräver fortfarande alla befintliga resursvillkor och en explicit separat opt-in. De historiska felkörningarna gör ingen NPU-succé sannolik förrän en ny, särskilt granskad plan föreligger. Ingen tidigare engångsworkflow återaktiveras. Ingen ändring av MyAI:s eller GenieX aktiva installation, udev, root, grupper, symlänkar, paket, ljud, kamera eller drivrutiner.

Efter gröna CI-resultat är nästa steg att bedöma exakta QNN-v75-backend- och DSP-processdomäninställningar utan att starta ny inferens. GitHub support purge PR #110 är separat releaseblockerare.
