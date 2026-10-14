# MyAI – CDSP firmware-sökvägar och processdomän, kontrollpunkt

Datum: 2026-10-14. Arbetsgren: dev/ventuno-cdsp-firmware-search-metadata-20261014. Endast DRAFT, ej produktionsdriftsatt.

## Verifierad tidigare status

- PR #164, commit `6ae07052969884806df07a60a34ade81b78c0e5e`: [riktig VENTUNO CDSP-metadata #38601453849](https://github.com/Harrokk/Myai/actions/runs/38601453849) visar 3 remoteproc running, varav en identifieras som CDSP via Device Tree och är **running**. CDSP firmware-attribut läsbart, men den begränsade namnheuristiken kände inte igen rånamnet som CDSP. Detta är INTE felbevis.
- PR #164 [full ARM64 CI #38601454018](https://github.com/Harrokk/Myai/actions/runs/38601454018): **1921 passed, 14 skipped**, static audit PASS med 0 blockerande fynd.
- `fastrpc_shell_unsigned_3` under /usr/lib/dsp/cdsp upplöstes till en vanlig Hexagon ELF. QAIRT 2.46, qcom FastRPC 1.0.15, paketerad Hexagon V75-Skel och ACL-baserad GenieX DMA-heap R/W verifierade i äldre utkast. HTP-initiering har fortfarande tidigare rapporterat `backend_initialization_failure` och är inte funktionellt verifierad.
- PR #163 gjorde V75-Skel-väljaren fail-closed, men inga utvecklings-PR:ar har slagits samman/installerats. Historikrensning/support-purge PR #110 förblir separat blockerare.

## Leverantörs- och kärndokumentation

Linux kärnans firmware search path-dokumentation beskriver /lib/firmware/updates/<kernel-release>/, /lib/firmware/updates/, /lib/firmware/<kernel-release>/ och /lib/firmware/ samt möjlighet till separat konfigurerat sökspår: https://docs.kernel.org/driver-api/firmware/fw_search_path.html

Linux beskriver att drivrutiner byggda in i kärnan kan få firmware från **initramfs** och att remoteproc kan involvera andra laddningsmekanismer. Avsaknad från rotfilsystemets sökvägar bevisar inte att en aktiv CDSP har fel eller saknar firmware: https://docs.kernel.org/driver-api/firmware/direct-fs-lookup.html

Qualcomm FastRPC-daemondokumentation skiljer på user PD, statiska processdomäner och default listeners; förekomsten eller frånvaron av en daemon är inte ett enkelt ja/nej på HTP: https://github.com/qualcomm/fastrpc/blob/development/Docs/daemons.md

## Nästa skrivskyddade diagnos

- `scripts/ventuno_cdsp_firmware_search_readonly.py` identifierar **exakt en** aktiv CDSP med samma namn/DT-klassificering som tidigare verifierad probe och läser högst 192 tecken av dess befintliga sysfs `firmware`-attribut.
- Validerar namnet som relativt segmenterat (inga `..`, absoluta sökvägar, mellanslag/kontrolltecken eller ovanliga filkomponenter); återger aldrig namnet.
- Kandidater undersöks endast med `exists/resolve/lstat` under de dokumenterade fyra sökvägarna, med metadata-only, max fyra kandidater. Länkar som lämnar den kanoniska firmware-rooten accepteras inte.
- Returnerar endast antal giltiga vanliga filer i provade sökvägar, om det finns länkar utanför tillåten root och om den validerade inställningen för extra kernel firmware path är tom/konfigurerad/otillgänglig. Ingen firmware-fil öppnas eller hashas; inga råa filnamn, länkmål, enhetsidentifierare eller personuppgifter publiceras.
- Nio syntetiska regressionstester täcker bland annat falska traversal-namn, fungerande fil, avsaknad av fil utan falsk slutsats, länk ut ur rot, begränsade sökvägar, tvetydiga processorer och dataskydd.
- Ett grenen-/workflowpath-scopat engångsmetadatajobb på self-hosted VENTUNO-kortet från exakt commit kör enbart denna kontroll i ett temporärt arbetsutrymme. Det är inte en global engångsspärr vid framtida workflowändringar.

## Stoppregler och tolkning

En lokal fil i en Linux-sökmapp visar **möjlig filnärvaro**, inte att just denna fil användes vid CDSP-uppstarten, att den är giltig firmware eller att dess byggversion matchar FastRPC shell/QAIRT v75. Ingen fil i sökvägarna betyder bara att filen inte hittades där; initramfs eller vendor mechanisms kan användas. Inget av dessa utfall godkänner ny HTP-run.

Ingen service-omstart, sudo/root, chmod/chown, udev/group/ACL ändring, firmwareläsning, installation, kerneländring, ny modell/NPU-körning, mikrofon/kamera eller PR-merge. Ingen produktion ändras.
