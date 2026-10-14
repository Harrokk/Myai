# MyAI checkpoint – QAIRT/HTP-v75-konfiguration på verklig VENTUNO Q

Datum: 2026-10-14. Utvecklingsgren: dev/ventuno-htp-v75-package-inventory-20261014. DRAFT; ingen driftsättning.

## Föregående mätningar som är verifierade

- [PR #158, full CI #38593832639](https://github.com/Harrokk/Myai/actions/runs/38593832639): **1880 passed, 14 skipped**, static audit PASS och 0 blockerande fynd. En äldre manuell `exec`-granskningspunkt finns kvar.
- [DMA-heap ACL #38593763496](https://github.com/Harrokk/Myai/actions/runs/38593763496): ACL-v2 parsad på riktigt kort. Runner och GenieX har båda beräknad rätt att läsa och skriva DMA-heap. Ingen faktisk open(2), AppArmor-utvärdering eller HTP-körning verifierades.
- [PR #154 HTP error #38585894311](https://github.com/Harrokk/Myai/actions/runs/38585894311): liten syntetisk 16 004-byte DLC gav `backend_initialization_failure`, inte HTP-inferens. [PR #153 CPU parity #38582751317](https://github.com/Harrokk/Myai/actions/runs/38582751317) fungerade och matchade CPU-referens.

## Källbaserat nästa steg

- Arduino VENTUNO Q-guide specificerar paketen `qairt-libs` och `qairt-dsp-binaries` för QNN HTP-delegate:
  https://docs.arduino.cc/tutorials/ventuno-q/getting-started-qc-ai-hub/
- Arduino dokumenterar HTP **v75**, med DSP-skeleton i `/usr/lib/dsp/cdsp/libQnnHtpV75Skel.so`:
  https://docs.arduino.cc/tutorials/ventuno-q/llama-cpp/
- Qualcomm beskriver att värd-Stub, DSP-Skel, QAIRT SDK, HTP-arkitektur och firmware måste vara kompatibla, att `ADSP_LIBRARY_PATH` kan behövas, och att modeller lämpligen kompileras och körs med samma QAIRT-version:
  https://www.qualcomm.com/developer/blog/2026/10/how-ai-models-reach-hexagon-npu-qairt-fastrpc-hexagon-explained

## Den nya kontrollerade inventeringen

- `scripts/ventuno_qairt_v75_package_readonly.py` frågar endast `dpkg-query -W` för en kort lista med publicerade paketnamn; tillåt bara kort validerad versionssträng, aldrig paketlistor med personliga uppgifter eller rå felutmatning.
- Exakt namn- och path-styrd `lstat` på kända QNN-Stub/Skel/HTP/ModelDlc/CPU/delegate/RPC-bibliotek under fyra angivna baskataloger. Symlänkar noteras som okända mål och följs aldrig. Ingen ELF körs, ingen modell läses, inget DSP/HTP-anrop görs.
- Tillåtet resultat är endast paketstatus, validerad version och filkategori (regular/symlink/absent/unknown). Version eller filnärvaro innebär **inte** verifierad kompatibilitet. Inga hårdvarunoder, systemd-tjänster, user-ID:n eller hemligheter kontrolleras eller skrivs ut.
- 6 isolerade regressionstester, plus full gemensam CI. Ett gren-/path-begränsat GitHub Actions-jobb använder exakt commit i temporärt arbetsutrymme, med cleanup. Det kör inte QNN.

## Bedömning och stoppregler

Tidigare HTP-backendinitiering misslyckades trots att bibliotek/fastRPC-noder fanns. Det är rimligt att nu undersöka om ett V75-Skel och rätt QAIRT-paket är installerade på den levande miljön, men denna metadatakontroll kan varken verifiera firmware-kompatibilitet eller prove DSP process domain.

**Ingen** apt-installation, uppgradering, chmod/chown, grupp-/udev-ändring, omstart, GenieX-konfigurationsändring, körning av liten eller stor HTP-modell, inspelning, kameraaktivering eller PR-merge. Alla ändringar hålls som DRAFT. Historisk GitHub Support purge i PR #110 är fortfarande en fristående releaseblockerare.

Nästa beslut fattas först efter verklig metadataoutput och full CI för exakt GitHub-commit. Vid package mismatch: gör dokumenterad risk- och rollback-granskning innan någon installation övervägs.
