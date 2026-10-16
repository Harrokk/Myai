# MyAI – oberoende pass 2: undantagsfel, verktygssvar och JSONL-integritet

**Datum:** 2026-10-16  
**Bas:** DRAFT #262 – granskning av historiska VENTUNO-jobb och Pythonberoenden.  
**Status:** Avslutas först efter egen exakt-commit ARM64 regression + syntetiska privacy-tester. Källkod och QA, inte fysisk driftsättning.

## Konstaterat riskmönster

I den manuella granskningen av `core/error_log.py`, `core/tool_manager.py`, `modules/internet/fetch.py`, `modules/files/workspace.py`, `modules/files/excel.py`, `modules/camera/capture.py`, `modules/location/gps.py` hittades att externa och native undantag skickade `str(error)` direkt till användarsvar eller JSONL.

Native Python-/OS-undantag kan innehålla privata absoluta sökvägar, URL-frågesträngar, API-nycklar eller andra hemligheter, även om verktygets avsikt bara var att visa ett enkelt fel. Tidigare `read_recent_errors` återgav dessutom gamla sparade råa meddelanden. Ett vanligt exception kan inträffa utan att verktyget behöver inneha särskilda rättigheter. Detta är en integritetsrisk, inte bevisat dataläckage.

## Åtgärder i DRAFT-grenen

1. `ErrorLogger.log_exception` skriver bara generisk svensk meddelandetext plus händelse, komponent och typ; inget `str(error)` persistieras.
2. `read_recent_errors` lämnar inte längre ut gamla råa `message`-värden från JSONL. Tidigare skapade loggfiler tas **inte** bort automatiskt, utan kräver en separat kontrollerad bevarings-/saneringspolicy.
3. `tool_manager._log_error` skickar ett anonymiserat undantag till eventuella loggplugins; `load_tools` och `run_tools` visar aldrig råa native undantag. Skyddad röstdispatch lämnas oförändrad.
4. Fem direkta modulfamiljer får samma anonymisering även om de själva fångar sitt undantag: web_fetch, workspace, Excel, GPS och kamera. De befintliga felprefixen behålls, så `result_failure_prefixes` och tool-outcomes kan fortsätta känna igen fel.
5. Syntetiska prov injicerar falska token-URL:er i undantag utan att öppna nät, Excel-filer, kamera eller seriell port. Regressionssviten kontrollerar avsaknad av dessa strängar i både resultat och felloggar.

## Vad skyddet INTE gör

- Felkategorier kan bli mindre detaljerade för användaren; framtida säkra maskinläsbara felkoder rekommenderas i stället för råa OS-feltexter.
- Tidigare loggfiler på aktivt installerad VENTUNO rensas eller skrivs inte om. Ingen installation eller deploy har skett.
- Detta skyddar specificerade identifierade vägar och är **inte** intyg om att alla 520 Python-filer har granskats manuellt rad för rad, eller att varje modul i projektet omöjligt kan exponera privata data.
- Oberoende säkerhetsbedömning av alla importkedjor och externa anrop, låsning av samtliga transitiva beroenden, QAIRT/native röst/HTP och operatörsnärvarande liveprov förblir öppna.

**Slutbeslut:** Kodkorrigeringarna kan testas separat, men ingen merge till main, modellkörning, fysisk ljudaktivering eller produktionsinstallation har godkänts.
