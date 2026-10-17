# MyAI – beroenderevision: installerad VENTUNO Python-miljö

**Datum:** 2026-10-17  
**Omfattning:** Fjärrbaserad, skrivskyddad metadataobservation på Arduino VENTUNO Q. **Ingen installation, modulimport, modellexekvering eller tjänsteändring.**  
**Baslinje:** [PR #267](https://github.com/Harrokk/Myai/pull/267), [Actions-körning #38958988194](https://github.com/Harrokk/Myai/actions/runs/38958988194), som lyckades för metadata- och syntetisk testkontroll.

## Vad som är bevisat från förra skrivskyddade körningen

| Fält | Installerad metadata i föregående körning |
| --- | --- |
| `requests` | 2.34.2 |
| `urllib3` | 2.8.0 |
| `psutil` | 7.2.2 |
| `arduino-router-bridge` | 0.5.0 |
| `faster-whisper` | Saknas i granskad Python-venv |
| `sounddevice` | Saknas i granskad Python-venv |
| `webrtcvad-wheels` | Saknas i granskad Python-venv |
| `pyttsx3` | Saknas i granskad Python-venv |
| Övriga tillåtna paketreferenser (PyAV, CTranslate2, OpenCV, OpenPyXL, Bleak, pyserial) | Saknas i granskad Python-venv |
| Antal installerade distributioner som metadata kunde räkna | 14 |
| Installerade nätverksminimum | Både Requests och urllib3 över kontrollerade säkerhetströsklar |
| Reell ljud- och modellkapacitet | **Ej verifierad** |
| Fullständig aktiv prodkonfiguration, native systembibliotek, ABI | **Ej verifierad** |

Detta beskriver det specifika Python-venv som kontrollen läste, inte varje Python-interpreter eller installerad programvarukomponent på VENTUNO. Frånvaro i denna miljö kan inte tolkas som att paketet saknas från alla andra systemmiljöer.

## Förnyad kontroll på integrerad revisionsgren

`scripts/ventuno_installed_dependency_metadata_readonly.py` hämtar enbart `importlib.metadata.version()` för 14 uttryckligen tillåtna distributionsnamn och ett aggregat av fördelningar. Inga Python-paket installeras eller importeras, inga modellfiler öppnas, inga servrar kontaktas och inga enheter används. Utdata innehåller **inte** användarens sökvägar, användardata, modellpromptar, terminalidentiteter eller råa metadatafel. Syntetiska tester avvisar saknade, äldre och tvetydiga paketversioner för säkerhetsminimum.

På den nya integrerade DRAFT-grenen görs en **ny** exakt-SHA-kontroll. Den tidigare gröna körningen gäller den tidigare separata grenen; den nya får inte markeras färdig förrän dess egna GitHub Actions är klara.

## Externa versionslås och sårbarhetsskanning

Den oberoende fullständiga pass-4-körningen för [PR #268](https://github.com/Harrokk/Myai/pull/268), [#39004731663](https://github.com/Harrokk/Myai/actions/runs/39004731663), körde `pip-audit` på **28 hashade röstpaketversioner** i en separat GitHub-hostad miljö: 28 poster, 0 rapporterade sårbarheter vid kontrolltillfället. Detta är en källbaserad version-/advisorykontroll och **bevisar inte** att dessa pakethjul är installerade eller native ABI-fungerar på VENTUNO.

## Öppna skyldigheter innan fullständig beroendeattestation

1. SBOM över alla **faktiskt installerade** Python- och OS-/nativepaket i den tänkta releaseprofilen, inklusive QAIRT/GenieX och firmwaregränssnitt, samt faktisk nedladdningskälla och signatur/verifierbar artefakthash.
2. Låsning av hela transitiva beroendegrafen, inte enbart 28 röstpaket och direkta `requirements-*.txt`-specifikationer.
3. Licens- och leveranskedjegranskning av beroenden och externa GitHub Actions.
4. Reproducerbart test av riktiga import-/ABI-kontrakt i separat VENTUNO-test-venv, med rollback, och separat fysiskt samtycke för mikrofon, TTS eller HTP.
5. **Ingen merge eller produktionsinstallation** innan dessa grindar är klara och godkända.

**Revisionsstatus:** Skrivskyddat installerat dependency-urval verifierat på separat tidigare körning; ny integrerad DRAFT-kandidat behöver egen CI. Komplett produktionsberoendegranskning fortfarande **ÖPPEN**.
