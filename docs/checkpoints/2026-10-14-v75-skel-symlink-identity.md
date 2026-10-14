# MyAI checkpoint – QAIRT HTP-v75 Skel-länk och paketidentitet

Datum: 2026-10-14. Fortsättning efter PR #159. DRAFT, ingen driftsättning.

## Verifierad tidigare status på riktig VENTUNO Q

- [PR #159 full CI #38594973581](https://github.com/Harrokk/Myai/actions/runs/38594973581): **1886 passed, 14 skipped** och statisk integritets-/källkodsgranskning PASS, inga blockerande fynd. En äldre manuell exec-granskning återstår.
- [QAIRT paket och filmetadata #38594879492](https://github.com/Harrokk/Myai/actions/runs/38594879492): `qairt-libs` och `qairt-dsp-binaries` installerade, båda **2.46.0-0ubuntu1~bpo24.04.1**. Host HTP, V75-Stub, CPU, ModelDlc och TFLite-delegate finns som vanliga filer i /usr/lib.
- V75-DSP-skeleton finns på Arduino-dokumenterad plats som **symlink**, men föregående inventering följde inte länken. Denna länk är nu föremål för verifiering.
- `libqnn1`/ `qnn-tools` rapporterades inte installerade eller inte verifierade, `libqnn-dev` var unavailable; detta är **inte** bevis att Arduino-installationen saknar nödvändiga komponenter eftersom dess officiella paket är de installerade `qairt-*`.
- [PR #158 ACL](https://github.com/Harrokk/Myai/pull/158): runnern och GenieX har enligt POSIX ACL-v2 beräknad R/W till DMA-heap. Detta motsvarar inte verifierad HTP-körning.
- [HTP-kategoritest #38585894311](https://github.com/Harrokk/Myai/actions/runs/38585894311) gav `backend_initialization_failure`, medan tiny CPU parity lyckades. HTP:s grundorsak är olöst.

## Varför symlänken granskas

Arduinos dokumentation nämner `/usr/lib/dsp/cdsp/libQnnHtpV75Skel.so` för VENTUNO HTP-v75:
https://docs.arduino.cc/tutorials/ventuno-q/llama-cpp/

Qualcomm beskriver att rätt DSP-Skel måste hittas och vara kompatibel med host-Stub, QAIRT och firmware:
https://www.qualcomm.com/developer/blog/2026/10/how-ai-models-reach-hexagon-npu-qairt-fastrpc-hexagon-explained

## Denna kodändring

- `scripts/ventuno_htp_v75_skel_link_readonly.py` gör exakt lstat/resolve/stat för Skel-länk och två kända hostfiler (utan att läsa in, dlopen eller exekvera någon fil), klassificerar bara typ och om slutmålet är en vanlig fil i /usr/lib/dsp.
- `dpkg-query -S` anropas på exakt tre kända systemfilnamn. Endast tillåtna paketnamn eller neutral felkategori kan exporteras, aldrig rå dpkg-utmatning eller målväg.
- Syntetiska regressionstester täcker giltig länk, extern/dangling länk, specialfil, paketinventering och icke-utläckande JSON.
- Gren-/path-begränsat GitHub Actions-jobb kör enbart denna metadataklassificering i temporär checkout.

## Stoppgränser

Denna kontroll kan verifiera att länken leder till en vanlig fil men inte att Skel är rätt binärformat för DSP, att firmware och bibliotek är kompatibla, att signed/unsigned PD stämmer eller att faktisk FastRPC/NPU-exekvering fungerar.

Inget sudo, chmod/chown, paketinstallation, symlinkändring, udev/gruppändring, omstart, QNN-run, USB-ljudtest, produktionsmerge eller deployment. PR #110:s historikpurge är separat releaseblockerare.
