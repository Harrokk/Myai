# MyAI – FastRPC-status: okänd eller aktiv GenieX får aldrig tillåta HTP-kollision

Datum: 2026-10-14. Ny DRAFT-gren `dev/ventuno-htp-geniex-fastrpc-unknown-nogo-20261014` på [PR #177](https://github.com/Harrokk/Myai/pull/177).

## Utgångsläge, verifierat före ändringen

- [PR #177 – full ARM64 CI #38630753018](https://github.com/Harrokk/Myai/actions/runs/38630753018): **2030 passed, 15 skipped**, statisk source/privacy-audit PASS, 0 blockerande fynd. PR är fortfarande utkast, ej installerad på VENTUNO.
- Tidigare CPU-referens kördes med den syntetiska modellen på QNN CPU och matchade exakt x86-resultat, men den **verifierade inte** HTP/NPU.
- Den experimentella HTP-koden är sedan tidigare avskild och kräver uttryckligt `MYAI_ALLOW_ONE_TINY_QNN_HTP_ATTEMPT=yes`, samtidigt som dess tidigare HTP-försök alla misslyckades med bl.a. `backend_initialization_failure`. Den gamla HTP Actions-workflowen är arkiverad/inert. Denna PR återaktiverar den **inte**.

## Konkret observerad brist i villkoren

Tidigare i `scripts/ventuno_tiny_qnn_htp_once.py::run_once()` var GenieX-spärren:

```python
live = summarize_service(Path("/proc"), main_pid_from_systemd())
if live.get("fast_rpc_secure_fd_open") is True:
    return no_go
```

Alla andra tillstånd (saknad MainPID, oläsbar proc, trunkerad FD-genomsökning, processer som hinner avslutas, en f.d. öppnad FastRPC-deskriptor, eller en faktiskt *aktiv* GenieX som inte råkar ha secure-FD öppen exakt vid avläsningen) tolkades som att testet fick fortsätta. Detta är en **möjlig risk för konkurrerande NPU-/DSP-åtkomst** och ska inte förväxlas med belagd samtidig körning i historiska test.

## Korrigering: konservativ NO-GO utan NPU-körning

- `scripts/ventuno_geniex_runtime_attestation.py` rapporterar nu även `complete_fast_rpc_fd_scan`. Den är True bara om **alla** observerade GenieX-processers FD-kataloger var läsbara, inga FD-listor överskred 512, och varje FD-länk gick att avläsa. Annars blir den False. Den befintliga `complete_process_maps` behålls separat.
- `assess_geniex_concurrency()` klassar **säker FastRPC-FD-open** som `no_go_existing_geniex_fastrpc_busy`. Saknad MainPID, ofullständig FD-/kartläsning eller annat oklart underlag ger `no_go_geniex_service_state_unknown`.
- Även om FD- och maps-läsningarna var fullständiga och ingen secure-FD syns, blockerar den **aktiva GenieX-processen** fortsatt andra HTP-klienter: `no_go_geniex_active_concurrent_htp_unsafe`. Ett process- eller fildeskriptorsnapshot kan aldrig garantera att GenieX inte börjar köra på NPU strax efter avläsningen. Eftersom avstängd GenieX-tjänst i denna diagnostik också är otillräckligt bekräftad är `run_once()` **avsiktligt inert i nuvarande kodväg** tills ett separat, leverantörsstött och uttryckligt godkänt körprotokoll etablerats. Det är ett säkerhetsstopp, inte ett nytt HTP-bevis.
- RAM-värdet hämtas dessutom **en gång**, i stället för två, för en konsekvent gränskontroll.
- Regressioner täcker okända och falska värden, ofullständigt processunderlag, aktiv GenieX utan öppen FD, faktisk upptagen FD, OSError vid FD-readlink, FD-scanbudget samt att även env-opt-in **inte** exekverar QNN vid okänd/aktiv GenieX.

## Skrivskyddad VENTUNO-status, separat från HTP

`scripts/ventuno_geniex_htp_concurrency_gate_readonly.py` läser endast `systemctl show --property=MainPID` och begränsade /proc-statusmetadata. Output är endast kategoristatus och booleska värden (ej PID, filväg, device-open eller rå diagnostik).

En separat path-scopead GitHub Actions-workflow använder `ventuno-q`-runnern med **exakt Git SHA**, `timeout 30s`, tillfällig isolerad checkout och oförändrad produktion. Den kör *inte* `qnn-net-run`, någon annan modell, audio, camera eller firmware. Den stoppar/ändrar inte GenieX.

## Återstående evidens och gränser

Ingen faktisk samtidighetsfrihet kan garanteras av snapshot på aktiv GenieX; ett framtida HTP-test måste genomgå ny riskgranskning om att GenieX är säkert och verifierat stoppad eller på annan nivå isolerad, och därefter separat explicit godkännande. Felsökningen av HTP-v75 kräver dessutom verifierad Qualcomm runtime-/operator- och signerad/osignerad PD-konfiguration; ett live QAIRT 2.46-molnkatalogsvar saknas.

Inga HTP/NPU-försök, tjänsteomstarter, paket-, firmware-, udev-, grupp-, ACL-, rättighets-, ljud-, kamera-, molnmodell-, GitHub-merge- eller produktionsändringar. Historisk GitHub Support-rensning i [PR #110](https://github.com/Harrokk/Myai/pull/110) är fortsatt separat releaseblockerare.
