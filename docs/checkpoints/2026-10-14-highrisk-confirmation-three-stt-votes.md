# MyAI checkpoint – tredubbel röstverifiering även av högriskbekräftelse

Datum: 2026-10-14. Separat **DRAFT**-utvecklingsgren `dev/ventuno-voice-confirmation-three-votes-20261014` på [PR #179](https://github.com/Harrokk/Myai/pull/179). Ingen merge eller driftsättning.

## Befintligt verifierat läge

- [PR #179 full VENTUNO ARM64 CI #38633487018](https://github.com/Harrokk/Myai/actions/runs/38633487018): **2054 passed, 15 skipped**, källkods-/privacy-audit PASS, 0 blockerande fynd.
- PR #179 kräver tre **skilda STT-instansobjekt** och minst två ordagrant överensstämmande normaliserade tolkningar för **högriskkommandot**. Fuzzy match gäller ofarliga frågor; semantisk bypass för högrisk är blockerad. Verkliga mikrofonsignaler och faktiskt modellbeteende är ännu otestade.
- Trots detta kunde `core/voice_pipeline.py::_handle_pending_confirmation` tidigare godkänna det efterföljande korta ordet `bekräfta` med **en enda primär STT** om dess confidence var minst `high_risk_confirmation_min_confidence`. De två backup-STT-instanserna användes bara om primärkonfidensen var lägre. En feligenkänd högkonfidensbekräftelse kunde därmed gå vidare mot assistenten utan nytt oberoende hörselunderlag. Detta var en **kodrisk**, inte ett dokumenterat missbruk.

## Utförd korrigering, när högriskbekräftelse är aktiverad

- **Varje** bekräftelse av ett väntande högriskkommando samlar **en primär och två separata backup-STT-instanser**, oberoende av primär confidence. Exakt **tre** unika instanser och minst **två normaliserade uttryckliga bekräftelsefraser** krävs för att gå vidare till redan befintlig verktygsplanskontroll. Duplicerad backup eller primär-STT räknas aldrig två gånger.
- Minst en observerad **explicit avbrytfras** från någon av de tre STT-instansobjekten ger `confirmation_cancelled`, rensar väntande kommando och verkställer inget. En explicit **negation** som `bekräfta inte` ger `confirmation_required`, inte bekräftad åtgärd, även om två andra sagt `bekräfta`. Enbart primärt `avbryt` fortsätter ge omedelbar avbrytning.
- Om det saknas STT-resurser, en backup kastar fel eller en tolkning är obekräftad ger systemet aldrig verkställning. Exceptions från backup exponeras inte i återrapporterad status. Om den begränsade bekräftelsetiden hinner löpa ut **under** backup-STT beräkningen kontrolleras klockan igen efteråt och väntande åtgärd tas bort.
- Ett lågt confidence-värde kan fortfarande stödjas av två övriga oberoende och uttryckliga STT-bekräftelser. En ensam hög confidence räcker däremot inte. Befintlig kontroll av eventuell ändrad verktygsplan och explicit verktygsauktorisation är kvar.
- Denna PR utökar **enbart den befintliga bekräftelsefunktionen** där `high_risk_confirmation_enabled=True`. Den tvingar inte på bekräftelse för en profil där funktionen är helt avaktiverad; detta är ett separat policyval som behöver riskgranskas om profilen förändras.

## Testning och begränsningar

- Befintliga tester för godkänd explicit bekräftelse uppdaterades så att även de två separata backup-STT-instansobjekten verkligen uppfattar `bekräfta`, i stället för att de implicit ignoreras.
- **Tio nya rent syntetiska regressioner** täcker ensam high-confidence (nekas), två av tre uttryckliga röster, backup-`avbryt`-veto, negation, duplicerad STT, primär som backup, fel i backup, fördröjd STT över timeout, frånvarande backuper och vanlig direkt avbrytning.
- Separat path-begränsat GitHub-hosted x86-test kör med enbart `pytest==8.3.5` i temporär venv. Ordinarie isolerad VENTUNO ARM64-CI testar fulla projektet. Ingen faktisk mikrofon, USB-ljud, riktig STT-inferens, GenieX- eller NPU-modell körs.
- **Kvarstående risk:** tre STT-instanser kan vara beroende av samma modell/ASR-familj och deras fel vara korrelerade. Majoritet är en säkerhetsspärr, inte kryptografisk identitets- eller användarautentisering. Ett återspelat externt `bekräfta` kan inte uteslutas av en textmajoritet ensam; all verklig högriskverkställning behöver dessutom kontrollerade behörigheter och godkännande.

**Ej gjort:** ingen ljud-/kameratillgång, QNN CPU/HTP, firmware, GenieX-start/stop, sudo/apt, grupp/ACL/udev, Qualcomm API, modelluppladdning, deployment eller merge. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk sekretessrensning/Support-cache är fortfarande separat releaseblockerare.
