# MyAI – kontrollpunkt: V75 Skel ELF-format och FastRPC-användarpaket

Datum: 2026-10-14. Status: DRAFT; ingen produktionsdriftsättning.

## Tidigare fastställt på verklig VENTUNO Q

- PR #160, commit `ed3e5f2b`: [CI #38596459440](https://github.com/Harrokk/Myai/actions/runs/38596459440) gav **1897 passed, 14 skipped**, statisk audit PASS med 0 blockerande fynd.
- [Skel metadata #38596265439](https://github.com/Harrokk/Myai/actions/runs/38596265439): `libQnnHtpV75Skel.so` är en fungerande symbolisk länk till en vanlig fil inom **/usr**, men utanför de snävt provade vendor-katalogerna; paketägarskapet för själva målfilen var därför fortfarande okänt.
- [QAIRT paket #38594879492](https://github.com/Harrokk/Myai/actions/runs/38594879492): `qairt-libs` och `qairt-dsp-binaries` är installerade i version **2.46.0-0ubuntu1~bpo24.04.1**.
- [DMA-heap ACL #38593763496](https://github.com/Harrokk/Myai/actions/runs/38593763496): både GenieX och runner har beräknad ACL-läs/skriv, utan bevis för verklig open eller HTP-körning.
- HTP-testet i #154 slutade med `backend_initialization_failure`. En fungerande CPU-backend är verifierad i #153. Ingen NPU-inferens är verifierad.

## Underlag

Arduinos officiella VENTUNO-guide dokumenterar v75 och platsen för Skel samt runtime-paketen:
https://docs.arduino.cc/tutorials/ventuno-q/llama-cpp/
https://docs.arduino.cc/tutorials/ventuno-q/getting-started-qc-ai-hub/

Qualcomm förklarar separat host Stub, DSP Skel, FastRPC och behov av kompatibla DSP-versioner:
https://www.qualcomm.com/developer/blog/2026/10/how-ai-models-reach-hexagon-npu-qairt-fastrpc-hexagon-explained

## Ny, begränsad kontroll

- `scripts/ventuno_v75_elf_fastrpc_readonly.py` följer den **exakt kända** Skel-länken och fortsätter endast om målfilen ligger inom /usr, är en vanlig fil och är storleksbegränsad.
- Skriptet använder `O_NOFOLLOW | O_NONBLOCK`, verifierar filidentiteten med `fstat` och läser högst **64 byte** för att klassificera ELF-header som Hexagon (EM_HEXAGON = 164), AArch64 (183), annan ELF eller okänd. Det **öppnar en vanlig biblioteksfil för läsning**, men varken laddar eller exekverar biblioteket och öppnar **ingen DSP-/FastRPC-enhet**.
- `dpkg-query -S` gör ett paketägarskapsuppslag på den lösta filens väg men returnerar bara namnet om det är `qairt-libs` eller `qairt-dsp-binaries`; inga andra paketnamn eller sökvägar lämnas ut.
- `dpkg-query -W` gör exakt två paketuppslag: `qcom-fastrpc1` och `qcom-fastrpc-dev`; status och kort validerad versionssträng returneras. Dessa paketnamn är indikativa, inte krav för samtliga VENTUNO-byggen.
- Endast `lstat` kontrollerar två kända sökvägar för `fastrpc_shell_unsigned_3`. Namnet "unsigned" bevisar inte vilken processdomän som faktiskt används.
- Sju isolerade regressionstester, GitHub Actions från exakt SHA i temporär checkout, ingen produktion, omstart eller ny HTP-modellkörning.

## Beslutsgräns

En Hexagon-ELF-header och ett matchande QAIRT-paket skulle visa binärformat och paketproveniens, **inte** firmware/ABI-kompatibilitet, DSP-körbarhet eller signerat/osignerat protection domain. En negativ provning visar bara utfallet för den samplade filen eller katalogen. Ändra inte sökvägar, symlänkar, runtime-paket, udev/gruppbehörigheter eller tjänster baserat på denna inventering utan separat vendorbekräftelse, rollback och uttryckligt godkännande.

MyAI-produktionen, ljud, kamera och GenieX är orörda. Historisk GitHub Support purge i PR #110 kvarstår som separat releaseblockerare.
