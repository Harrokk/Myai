# MyAI checkpoint – valfri säker live-läsning av Qualcomms QAIRT-katalog

Datum: 2026-10-14. Ny gren `dev/ventuno-qai-hub-live-catalog-readonly-20261014`, på PR #172. **Endast DRAFT; ingen merge, installation eller driftförändring.**

## Verifierat innan denna ändring

- [PR #172 full isolerad ARM64 CI #38623617814](https://github.com/Harrokk/Myai/actions/runs/38623617814) **2000 passed, 15 skipped**, statisk source/privacy-granskning PASS med 0 blockerande fynd.
- [PR #172 x86 snapshot-säkerhet #38623499414](https://github.com/Harrokk/Myai/actions/runs/38623499414): 23 syntetiska tester godkända, ingen autentiserad Qualcomm-katalog läst. `ai_hub_version_246_listed=True` kan inte längre felaktigt klassas som live-verifierad.
- [Qualcomm Working with Frameworks](https://workbench.aihub.qualcomm.com/docs/hub/frameworks.html) anger `client.get_frameworks()` och [Client API](https://workbench.aihub.qualcomm.com/docs/hub/generated/qai_hub.Client.html) anger `client.get_devices(name="Arduino VENTUNO Q")` som separata **läsanrop**. API:et stödjer också aktivt skrivande jobb, men **inga sådana metoder förekommer i denna kontroll**.
- [Arduino VENTUNO Q](https://docs.arduino.cc/tutorials/ventuno-q/getting-started-qc-ai-hub/): officielt mål `Arduino VENTUNO Q` på Ubuntu 24.04; `QCS8275 (Proxy)` är Android-mål. Använd inte Android-proxyn som likvärdigt bevis för exakt kort.
- QAIRT 2.46 finns installerat på verklig VENTUNO och den syntetiska DLC-fixturen fungerar med QNN CPU. Det finns ännu **inget autentiserat Qualcommsvar som visar att 2.46 erbjuds i molnkatalogen**, ingen HTP-v75 operator-/kontextverifiering och ingen fungerande NPU-inferens.

## Ny funktion, explicit valfri, bara på betrodd x86-host

`scripts/ventuno_qai_hub_live_catalog_readonly.py` innehåller en endaste nätverksmöjlighet:

1. **Standardläget** utan flaggor använder **inte** Qualcomms klient, importerar den inte, kommer inte åt API-token eller nätverk och rapporterar `no_go_readonly_api_not_authorized`.
2. Med kommandot `--confirm-readonly-api` på en separat betrodd **x86_64/amd64**-dator där användaren själv redan har installerat en legitim Qualcomm `qai_hub`-klient och konfigurerat åtkomst, får koden endast skapa `Client()` och göra exakt **två** SDK-läsningar: `get_frameworks()` samt `get_devices(name="Arduino VENTUNO Q")`. ARM64/VENTUNO får alltid `no_go_host_must_be_x86`.
3. Om ett strukturerat live-svar innehåller QAIRT `api_version="2.46"` med konsekvent `full_version`, och Qualcomm samtidigt returnerar den *exakta* Ventuno-enheten i enhetslistan, ges endast **`read_only_catalog_and_target_listed_htp_unverified`**. Det betyder att klienten *rapporterar* båda i samma lässession, **inte** att 2.46 för just VENTUNO är en bekräftat tillåten compile/link-kombination eller att HTP stöder vår graf.
4. Svar med över 256 ramverk / 32 enheter, tvetydig QAIRT-2.46-post, fel version, andra enhetsnamn, nätverksfel och ogiltiga svar ger aldrig GO. Alla råa klientutskrifter och exceptions döljs; koden skriver enbart kontrollerade kategorier och booleska fält, **inte** kontouppgifter, token, sökvägar eller personliga enhetsnamn.
5. Kodvägen saknar modellhantering och metoder för `upload_model`, `submit_compile_job`, `submit_link_job`, `submit_inference_job`, kontextbyggnad och drift av QNN. **Ingen uppladdning eller jobbinlämning är tillåten av en framgångsrik katalogläsning.**

**Begränsning:** Det här är ett SDK-baserat *observationsresultat*, ingen kryptografisk attestering av SDK-/serveridentitet eller en garanti att ramverket finns för varje enskilt chip i compile/link-flödet. Säker TLS, behörig Qualcomm-inloggning och klientproveniens måste granskas före en framtida manuell körning. Man ska **inte** spara tokens i GitHub Actions secrets för denna förberedelse.

## Verifiering utan externt API

- `tests/test_ventuno_qai_hub_live_catalog_readonly.py` innehåller 12 **syntetiska** fall med injicerad låtsas-klient: standard NO-GO, ARM-avslag, exakt två tillåtna läsmetoder, 2.45/2.50 utan 2.46, proxy-nej, inkonsekvent `full_version`, dubbla poster, fel datastruktur, undantag/hemligheter och avsaknad av modelljobb.
- `.github/workflows/ventuno-qai-hub-live-catalog-safety.yml` är branch-/path-scopat med exakt commit, temporär GitHub-hosted x86 checkout och endast `pytest==8.3.5` installerat i temporär venv. Det **saknar `--confirm-readonly-api`**, har inget `qai_hub` installerat, använder inga autentiseringsuppgifter och gör inga Qualcomm-anrop.
- Projektets ordinarie isolerade ARM64-CI kontrollerar all Pythonkod och regressionssviten utan att anropa API:t eller ändra installerad MyAI.

## Fortsatt NO-GO för HTP och molnkompilering

Avsaknad av användarens autentiserade Qualcomm-klient betyder att ett **faktiskt live-svar fortfarande saknas**. Enbart verifierad tjänsteläsning skulle kunna avlägsna blockeraren "2.46 är inte listad", **inte** blockerarna exakt VENTUNO compile/link-stöd, V75-grafoperatorer, DSP/PD-konfiguration, faktisk NPU-placering eller QAIRT-kompatibilitet på det installerade kortet. Ingen modellöverföring, Cloud Compile, installation, NPU-körning eller produktion skall ske automatiskt.

Historisk GitHub Support-cache/history purge i [PR #110](https://github.com/Harrokk/Myai/pull/110) är fortfarande fristående releaseblockerare.
