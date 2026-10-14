# MyAI checkpoint – säker identifiering av exakt Qualcomm VENTUNO Q Ubuntu-mål

Datum: 2026-10-14. DRAFT-gren `dev/ventuno-qai-catalog-exact-os-failclosed-20261014` på PR #173. Ingen produktion installerad, inga tjänster ändrade.

## Korrigerad kontroll av riktig mål-OS

Qualcomms [Client.get_devices](https://workbench.aihub.qualcomm.com/docs/hub/generated/qai_hub.Client.html) accepterar **name** och **os** som två explicita filter. [Device-objektet](https://workbench.aihub.qualcomm.com/docs/hub/generated/qai_hub.Device.html) har också `name` och `os` som strukturerade fält. [Arduino-guiden](https://docs.arduino.cc/tutorials/ventuno-q/getting-started-qc-ai-hub/) skiljer på `Arduino VENTUNO Q` (Ubuntu 24.04) och `QCS8275 (Proxy)` (Android 14).

Tidigare [PR #173](https://github.com/Harrokk/Myai/pull/173) gjorde läsning av `get_frameworks()` och `get_devices(name="Arduino VENTUNO Q")` möjlig **endast på betrodd separat x86-värd och efter explicit flagga**. Dess resultatanalys kontrollerade bara enhetens namn. Det var en faktisk för svag validering eftersom OS-filtret inte bekräftades.

Detta steg:
- Kräver `get_devices(name="Arduino VENTUNO Q", os="24.04")`, exakt dokumenterad målprofil.
- Validerar att svaret innehåller **en enda post** med både `name == "Arduino VENTUNO Q"` och `os == "24.04"`. Tomt svar eller fel OS ger NO-GO, fel format/dubletter klassas som osäkert/tvetydigt svar. Ingen Android-proxy eller gammal/multiplattformspost godtas.
- Publikt resultatfält `exact_ubuntu_2404_target_verified` visar enbart sann/falsk; inga andra enhetsnamn, versionssträngar eller personuppgifter exporteras.
- Qualcomm API-klientens oväntade stdout/stderr kastas i en skriv-sväljare, i stället för tidigare `StringIO` som kunde ackumulera godtyckligt stora privata fel-/diagnostikmeddelanden i RAM. En del externa C-/operativsystemloggar kan ligga utanför Pythons stdout/stderr-omdirigering; en autentiserad framtida klientkörning måste därför hållas isolerad och granskad.
- Ingen förändring i behörighetsgrinden: utan `--confirm-readonly-api` importeras Qualcomm inte och inga credentials eller nätverk används. På ARM/VENTUNO avbryts fortfarande alla läsningar.
- Även ett positivt *framtida* katalogsvar som visar både enhet och QAIRT 2.46 bevisar **inte** att just denna 2.46-graph/compile-/link-konfiguration är tillåten, eller att HTP-v75 fungerar. Ingen modell skickas.

## Verifiering

- [Separat GitHub-hostad x86 Actions #38625411176](https://github.com/Harrokk/Myai/actions/runs/38625411176): **17/17 tester godkända**. Testar falsk Qualcomm-klient, saknat samtycke, fel OS, exakt namn, Android-proxy, dubbla poster, isolerade klientfel, loggdämpning samt att inga skrivande molnmetoder körs.
- Den ordinarie isolerade ARM64-sviten verifieras separat vid exakt senaste HEAD. En tidig intermediate-kodcommit `084e9f31` fick regressioner eftersom den hade uppdaterat API-signaturen innan syntetiska klienttester följde med; testerna uppdaterades i commit `1468447a`. Den version som skall avgöra statusen är sista commit inklusive checkpoint, inte detta mellanläge.

## Återstående blockerare

Ingen verklig autentiserad live QAIRT `get_frameworks()` har utförts. Ingen användartoken är ansluten och inga uppgifter har skickats till Qualcomm. Framför allt kvarstår HTP-operatörsstöd, firmware/PD- och ABI-kompatibilitet, korrekt målkontext och bevis för faktisk NPU-exekvering.

Ingen modelluppladdning, molnkompilering, QAIRT-nedladdning, HTP/NPU, firmware/udev/ACL/gruppändring, service-omstart, kamerastart, ljud, merge eller produktionsdriftsättning. PR #110 historisk GitHub Support secret-history-purge kvarstår separat releaseblockerare.
