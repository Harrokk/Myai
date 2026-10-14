# MyAI checkpoint – CDSP remoteproc och FastRPC unsigned shell

Datum: 2026-10-14. Gren: dev/ventuno-cdsp-remoteproc-shell-readonly-20261014; enbart DRAFT, ingen installation eller merge.

## Faktiskt verifierat sedan tidigare

- [PR #163, CI #38598773324](https://github.com/Harrokk/Myai/actions/runs/38598773324): **1912 passed, 14 skipped**, statisk source/privacy-audit PASS och 0 blockerande fynd.
- [PR #162, riktig VENTUNO jämförelse #38598267753](https://github.com/Harrokk/Myai/actions/runs/38598267753): äldre Skel-väljare pekade på annan dev/inode än paketerad V75-Skel. Detta motiverade fail-closed-korrigering i PR #163 utan att något HTP-prov utfördes.
- [PR #161, riktig VENTUNO #38597705438](https://github.com/Harrokk/Myai/actions/runs/38597705438): verifierad Hexagon ELF för officiella V75-Skel som ägs av qairt-dsp-binaries, FastRPC användarpaket installerade.
- QNN CPU-inferens av tiny DLC fungerade i PR #153; tidigare HTP-inferens misslyckades, senaste HTP error category backend_initialization_failure. **NPU-drift är inte verifierad.**

## Källstöd och osäkerheter

- Qualcomms FastRPC-daemondokumentation förklarar att dynamiska user PD-beräkningar kan fungera utan daemon, medan vissa statiska PD och reverse-RPC-funktioner behöver listener. Därför ska avsaknad av en specifik daemon **inte** automatiskt vara ett HTP-fel:
  https://github.com/qualcomm/fastrpc/blob/development/Docs/daemons.md
- Qualcomms rapport om dsp_check:s tidigare hårdkodade systemvägar visar att `dsp_check` kan redovisa missvisande firmware-/PD-stöd på vissa Debian/Ubuntu-system. Kör inte verktyget för att få ett enkelt ja/nej utan att granska versionsberoendet:
  https://github.com/qualcomm/fastrpc/issues/385
- I ett separat Qualcomm-fall var DSP-firmware och FastRPC-shell från skilda byggen och initiell PD-uppstart misslyckades. Detta är endast en **hypoteskategori**, inte något verifierat om VENTUNO:
  https://github.com/qualcomm/fastrpc/issues/377

## Ny strikt läskontroll

- `scripts/ventuno_cdsp_remoteproc_shell_readonly.py` läser endast allowlistade `/sys/class/remoteproc/remoteprocN/{name,state,firmware}` med hårda läs- och antalsgränser. Skriver endast antal och kategorier samt om en ensam identifierad CDSP-enhet är `running`, `offline` eller okänd.
- Rå firmware-sökväg, remoteproc-namn, DSP-serienummer och firmware-byggsträngar skrivs inte ut. Firmware-filen öppnas **inte**. Endast existens och heuristisk CDSP-namngivning av sysfs-attributet observeras.
- Under två exakta kända FastRPC-shell-sökvägar `/usr/lib/dsp/cdsp/fastrpc_shell_unsigned_3` och `/usr/lib/dsp/fastrpc_shell_unsigned_3` följs endast en vanlig fil under /usr, med fstat-identitetskontroll och högst 64 bytes header för att klassificera ELF-arkitektur. Inget bibliotek laddas, ingen DSP device öppnas, inga konfigurationer ändras.
- Sju syntetiska regressionstester täcker korrekta och motstridiga DSP-namn, firmware-attribut utan läckage, fler än max enheter, shell-klassificering och nej till obevisade processdomänpåståenden.
- Det enda särskilda workflowet kör exakt commit i tillfällig runner-checkout, utan HTP, GenieX, audio/camera eller serviceändring. Varje ny ändring i workflowfilen kan trigga ytterligare metadatakörning; ingen global engångsspärr utlovas.

## Stoppregel

En rapporterad CDSP som "running" och en Hexagon ELF unsigned shell är **inte** likvärdigt med lyckad signerad/osignerad session, korrekt firmware/build matchning eller QNN HTP-inferens. Ingen apt, sudo, chmod/chown, grupp-/udev-ändring, omstart, kerneländring, nytt modellprov eller main-merge får göras i detta steg.

Historisk GitHub Support purge, PR #110, är fortfarande separat releaseblockerare. Nästa steg efter nytt CI och sann metadatamätning är att avgöra om en fullständigt dokumenterad, *icke-invasiv* firmware-/processdomän-granskning fortfarande behövs.

## Första verkliga resultatet och riktad förbättring

[GitHub Actions 38601049337](https://github.com/Harrokk/Myai/actions/runs/38601049337), riktig VENTUNO, genomfördes framgångsrikt:
- Tre remoteproc-enheter räknades, men ingen kunde klassificeras som CDSP enbart utifrån `name`-attributets säkra ordmatchning. CDSP-status är därför **unknown**, inte att processorn saknas eller är avstängd.
- `/usr/lib/dsp/cdsp/fastrpc_shell_unsigned_3` upplöstes till en vanlig biblioteksfil under /usr med **Hexagon ELF-header**. Kandidaten direkt under /usr/lib/dsp kunde inte klassificeras som tillgänglig. Det bevisar inte vilken shell som faktisk DSP-PD-session skulle välja.
- Ingen FastRPC-/DSP-enhet öppnades och ingen HTP-körning skedde.

Uppföljningskod använder nu dessutom endast den fysiskt befintliga remoteproc-enhetens begränsat lästa Device Tree `device/of_node/compatible` för att identifiera CDSP när namnet är opakt. Hela DT-strängen och enhetsadresser exporteras aldrig. Dessutom rapporteras **antal remoteproc som är running**, utan att det förväxlas med ett särskilt CDSP. Om klassificeringen inte är säker blir resultatet fortsatt unknown.

Dessa nya fält måste verifieras i en separat workflow-körning på exakt ny SHA innan någon slutsats om CDSP:s tillstånd dras.
