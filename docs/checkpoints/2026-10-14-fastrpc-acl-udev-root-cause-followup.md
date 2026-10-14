# MyAI VENTUNO Q – FastRPC ACL, processkapabiliteter och udev-rotrelationer

Datum: 2026-10-14. Föregående verifierade gren: PR #156 (commit a5317cf1).

## Riktigt verifierat på VENTUNO 14 oktober

- [GitHub Actions 38591578635](https://github.com/Harrokk/Myai/actions/runs/38591578635): **1864 passed, 14 skipped**, static audit **PASS**, inga blockerande fynd. En manuell granskning av tidigare känd exec-referens återstår. Detta är isolerade kodtester, inte godkänd NPU-inferens.
- [38591138757](https://github.com/Harrokk/Myai/actions/runs/38591138757) och [38590026057](https://github.com/Harrokk/Myai/actions/runs/38590026057) utförde verklig men skrivskyddad metadata-inventering på VENTUNO och returnerade båda samma huvudfynd:
  - FastRPC-gruppen existerar; runnern och GenieX tillhör gruppen.
  - Vanlig CDSP: effektiv och klassisk läs/skriv för runner och GenieX.
  - Säker CDSP: läs ja, skriv nej för både runnern och GenieX utifrån respektive metadata.
  - DMA-heap/system: runnerns **effektiva** läs/skriv ja, men klassisk DAC-läs/skriv nej både för runner och GenieX; nodens grupp matchar inte fastrpc-gruppen. **Detta betyder inte att GenieX saknar faktisk åtkomst.**
  - udev-inventering: 146 regel-filer lästa; 5 nämner dma_heap, 2 fastrpc, men `scan_complete=false`. Orsaken ännu ej känd – en länkad /lib-katalog är en möjlig förklaring, inte ett uppmätt faktum.
  - Inga device-open eller HTP-inferenser gjordes.
- Båda metadata-körningarna godkändes, men framgång för en read-only probe betyder inte framgång för QNN på HTP.

## Vendorbakgrund och gränser

- Qualcomm FastRPC `README.md` beskriver fastrpc-grupp med `0640` på DSP-noder och möjlig rättighetsstyrning för DMA heap: https://github.com/qualcomm/fastrpc/blob/development/README.md
- Qualcomm FastRPC issue #366 tar upp icke-root-användares DMA-BUF-behörigheter och rapporterad QNN-felsituation. Detta bevisar inte att vår VENTUNO har samma fel: https://github.com/qualcomm/fastrpc/issues/366
- Ingen rättighetsändring bör göras utifrån endast DAC/os.access; ACL, Linux capabilities, LSM/AppArmor, signed PD, firmware och verktygsversion kan påverka.

## Nästa snäva kontroll (separat DRAFT, EJ driftsatt)

`scripts/ventuno_fastrpc_acl_root_readonly.py` returnerar enbart:
- Fast udev-rottyp (etc, usr_lib, lib) och om lib och usr_lib refererar till samma katalog-inod. Inget innehåll eller namn på länkmål exporteras.
- För exakt två fördefinierade char-dev-noder (DMA heap och secure CDSP): status om POSIX ACL xattr finns/inte exponeras/inte stöds/inte åtkomlig. Xattr-bytes kastas och loggas aldrig. Ingen enhet öppnas.
- Boolesk indikator om CapEff innehåller någon bit för runnern respektive en enda identifierad GenieX-process. Inga capability-värden, PID eller UID/GID loggas.
- Om den tidigare observerade skillnaden mellan runnerns effektiva DMA-skrivrätt och klassiska DAC-skrivrätt kvarstår.

ACL xattr kan saknas eller vara oåtkomlig även om åtkomsten påverkas av andra mekanismer; läget är en indikator, inte en slutlig open(2)-kontroll.

### Exkluderat

Ingen chmod/chown, gruppjustering, udev-omladdning, root/sudo, nytt QNN/HTP-anrop, ljud/camera, systemd-omstart, processmanipulation, produktionsinstallation eller merge till main. Historikrensning/support-purge i PR #110 kvarstår som separat blockerare.

**Nästa beslut:** invänta faktiskt jobbresultat med exakt SHA; analysera metadata kategoriskt och ta endast därefter beslut om ny vendor-granskning. Inga privilegierade steg utan särskilt tydligt godkännande och återställningsplan.
