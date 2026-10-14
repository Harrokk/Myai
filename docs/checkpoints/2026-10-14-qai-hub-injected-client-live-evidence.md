# MyAI – klientproveniens för Qualcomm-katalog: syntetiskt får aldrig bli live-bevis

Datum: 2026-10-14. Gren `dev/ventuno-qai-client-provenance-failclosed-20261014`, på tidigare [PR #174](https://github.com/Harrokk/Myai/pull/174). **DRAFT, inga installationer eller merges.**

## Verifierat före ändringen

- [PR #174 ARM64 CI #38625570360](https://github.com/Harrokk/Myai/actions/runs/38625570360): **2017 passed, 15 skipped**, statisk källkods-/integritetsaudit PASS med 0 blockerande fynd.
- [PR #174 separata GitHub-hosted x86-tester #38625411176](https://github.com/Harrokk/Myai/actions/runs/38625411176): **17/17 syntetiska tester**. Skärpt dokumenterat Qualcomm API-anrop till `get_devices(name="Arduino VENTUNO Q", os="24.04")` och exakt ett matchande Device-objekt. Ingen verklig Qualcomm-katalog lästes.
- [Qualcomm Client API](https://workbench.aihub.qualcomm.com/docs/hub/generated/qai_hub.Client.html) dokumenterar `get_frameworks()` respektive `get_devices(name, os)`, och [Qualcomm Device API](https://workbench.aihub.qualcomm.com/docs/hub/generated/qai_hub.Device.html) dokumenterar separata namn-/OS-fält. [Arduino](https://docs.arduino.cc/tutorials/ventuno-q/getting-started-qc-ai-hub/) bekräftar VENTUNO Q Ubuntu 24.04 och Android-proxyn som ett annat mål.

## Konkreta säkerhetsfelet

I `scripts/ventuno_qai_hub_live_catalog_readonly.py` accepteras en `client_factory` som testinjektion för att undvika riktiga nätverksanrop. I PR #174 kunde en injicerad testklient som returnerade till synes korrekta `Framework(name="QAIRT",api_version="2.46")` och `Device(name="Arduino VENTUNO Q",os="24.04")` ge:
- `live_qairt_246_catalog_reported=true`
- `status="read_only_catalog_and_target_listed_htp_unverified"`

**Detta var ett bevisfel:** datan kom från en **injicerad fake-klient**, inte från Qualcomms autentiserade tjänst. Fortsatt användning av sådant resultat skulle kunna leda felsökningen i fel riktning.

## Ny fail-closed kontroll

- `run_readonly_query()` noterar nu om `client_factory` är injicerad före klientinstansiering.
- Rapporter från injicerad klient får `source_is_injected_client_not_attested=true` och får **aldrig** `live_qairt_246_catalog_reported=true`.
- Även en perfekt formaterad syntetisk katalog och rätt Ubuntu-mål ger bara `injected_catalog_fixture_only_not_live_verified`. Resultatet får visa parsad testdata, men inget autentiserat versionsstöd eller kompileringstillstånd.
- Utan `--confirm-readonly-api` sker fortsatt **inga** Qualcomm-klientimporter, autentiseringar eller nätverksanrop. ARM/VENTUNO nekas fortfarande.
- Endast en framtida separat autentiserad x86-körning via standard-SDK-klienten, efter avsiktligt opt-in, skulle kunna rapportera en läsobservation. Inte heller då bevisar katalogen `2.46` att en specifik compile/link-kombination, vårt ONNX-grafstöd eller HTP-exekvering fungerar.

## Verifiering och säkerhetsgräns

- Tre nya regressionsfall plus uppdaterat befintligt fall. Exakt matchande fake-klient måste förbli icke-autentiserad; saknat opt-in måste avstå helt; testklient med annan version får inte markeras live.
- Separat GitHub-hosted x86-workflow med temporär checkout och endast `pytest==8.3.5` i temporär venv, **ingen Qualcomm SDK eller token**, och inget `--confirm-readonly-api`.
- Ordinarie isolerad ARM64 CI verifierar resten av MyAI utan att ändra aktiv installation.
- Ingen cloudmodell, API-token, modelluppladdning, HTP/NPU-inferens, QNN-kontext, tjänsteomstart, grupp/ACL/udev, firmware/ljud/kamera, driftsättning eller merge.
- [PR #110](https://github.com/Harrokk/Myai/pull/110), historisk secret purge och GitHub Support-cache, kvarstår fristående releaseblockerare.

**Beslutsstatus:** Fortfarande NO-GO för verklig HTP-kompilering och test. Vi har inte ett autentiserat QAIRT 2.46-katalogsvar och inga verifierade HTP-v75-operator-/processdomänresultat för vår modell.
