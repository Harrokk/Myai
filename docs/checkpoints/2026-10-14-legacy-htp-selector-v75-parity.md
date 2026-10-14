# MyAI checkpoint: äldre HTP-testets DSP-sökväg kontra paketerad V75-Skel

Datum: 2026-10-14. DRAFT; inga produktionsändringar.

## Fastställd grund

- [PR #161 real read-only probe #38597705438](https://github.com/Harrokk/Myai/actions/runs/38597705438): `libQnnHtpV75Skel.so` är en riktig **Hexagon ELF** och målfilen ägs av `qairt-dsp-binaries`. `qcom-fastrpc1` och `qcom-fastrpc-dev` finns i version 1.0.15+repack2. `fastrpc_shell_unsigned_3` i /usr/lib/dsp/cdsp är en länk. Detta **bevisar inte** HTP-initiering.
- [PR #161 CI #38597788456](https://github.com/Harrokk/Myai/actions/runs/38597788456): **1904 passed, 14 skipped**, static audit PASS, 0 blockerande fynd.
- Den mycket lilla verifierade modellen fungerar på QNN CPU men tidigare HTP-försök gav `backend_initialization_failure`. Ingen ytterligare HTP-testning är tillåten på antaganden.

## Ny konkret observation från kodgranskning

Funktionen `_find_v75_skel_directory()` i `scripts/ventuno_tiny_qnn_htp_once.py`, som användes av tidigare HTP-försök med explicit DSP-sökväg, söker bl.a. /usr/lib/rfsa/adsp, /vendor/dsp, /opt/qcom, /opt/qualcomm och en GenieX-katalog. Den **inkluderar inte** Arduinos dokumenterade /usr/lib/dsp/cdsp och **ignorerar alla symlänkar**. Den paketerade V75-Skel på Arduino-katalogen har verifierats som just en symlink. Det innebär att tidigare valda reservfilen inte automatiskt är samma fil som VENTUNO:s officiella DSP-Skel.

Detta är en **möjlig konfigurationsavvikelse i vår HTP-testkod**, inte bevis för att avvikelsen faktiskt orsakade backend-felet eller att produktions-GenieX använder samma path.

## Denna uppföljning

- `scripts/ventuno_htp_dsp_selector_parity_readonly.py` anropar endast den äldre filkatalogväljaren (stat/filnamn, ingen QNN-körning), hämtar filidentitet för vald V75-Skel och jämför mot den verifierade paketerade Skel-länkens upplösta dev/inode.
- Ingen verklig filväg, inod, ägaridentitet, användarsträng eller modellinformation exporteras; endast boolean eller `null` vid okänt.
- Fem isolerade regressionstester skiljer mellan samma inode, annan kopia, saknad reservkopia och okänd kanonisk fil.
- En gren-/path-begränsad GitHub-runner-kontroll utför endast denna statiska jämförelse. Inga befintliga HTP-exekveringsskript ändras eller aktiveras.

## Nästa beslut

Om väljaren använder annan fil: verifiera version och kompatibilitet innan någon ändring av framtida testmiljö. Utforma en separat, granskad ändring som prioriterar installerad QAIRT-Skel utan att öka antalet NPU-prov. Om samma fil: leta vidare mot DSP process domain/firmware, men skapa inte blind HTP-retry.

Förbjudet: sudo, chmod/chown, symlinkändring, udev/grupp/apt-installation, service-omstart, HTP/NPU-modellkörning, kamerastart, ljudinspelning eller produktions-merge. PR #110 historisk GitHub-purge kvarstår som separat releaseblockerare.
