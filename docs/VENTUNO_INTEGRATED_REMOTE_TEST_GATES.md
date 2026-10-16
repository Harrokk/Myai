# MyAI VENTUNO – integrerad fjärrgrind före fysisk test

**Status 2026-10-16:** isolerad DRAFT-integrationskandidat, inte `main` eller installerad VENTUNO. Ingen ljudinspelning, hårdvarubelastning, paketinstallation i enheten, tjänsteändring eller modellstart är godkänd här.

## Verklig integration i en separat gren

Kandidaten skapades med **två Git-föräldrar**: granskad DRAFT PR #239 och `main` commit `f125fe6dc9abd6b27747f86d440fbb77b0602e58`. Den har därmed `main` i sin Git-historia, men har **inte** slagits samman med `main`. De fyra `main`-unika arbetsflödena har i kandidatens träd ersatts med inerta arkivfiler:

- `ventuno-full-dev-validation.yml`
- `ventuno-integration-validation.yml`
- `ventuno-regression.yml`
- `ventuno-runner-check.yml`

Varje arkivjobb har `if: false`, bara manuell trigger (ingen push), ingen self-hosted runner och inga kommandon för installerad kod, ljud eller HTP. Detta är ett avsiktligt **säkerhetsval**: ursprungliga `main`-filer har inte vidareutvecklats okontrollerat, och tidigare resultat för äldre grenar ska inte användas som ny fysisk körningsauktorisering. `scripts/ventuno_main_workflow_quarantine.py` nekar varje modifiering som förlorar spärren.

Först efter exakt SHA-låst CI, manuell diff- och integrationsgranskning kan en framtida **separat** release diskuteras. Att göra en temporär merge-commit är inte att distribuera.

## Röstpaket och reproducibilitet

`requirements-voice.txt` innehåller intervall för `faster-whisper`, `sounddevice`, `webrtcvad-wheels` och `pyttsx3` och är inte en låst install. Den installerade VENTUNO Python-venv:n saknade vid senaste kontrollen alla fyra. En framtida kompatibel, separat staging-venv kräver:

1. En manuellt granskad kompatibel **Python 3.12 + aarch64**-wheeluppsättning för varje toppnivåberoende och samtliga transitiva krav.
2. Kontroll av faktiska hjulnamn, ABI-taggar, SHA-256-hashar och frånvaro av otestade källkodskompileringar.
3. Reproducerbar offline-installation **i en egen temporär venv**, **inte** i `/home/arduino/MyAI/.venv`.
4. Fristående kontroll av CTranslate2/OpenMP, PortAudio, PyAV, ALSA, pyttsx3:s eSpeak och eventuell annan runtime ABI, **utan att ljudenhet öppnas**.
5. Därefter separat enhets-/modell-/prestandatest med nytt godkännande.

`scripts/ventuno_voice_wheelhouse_gate.py` är *endast* en offline kontroll av ett färdigt `wheelhouse.lock.json` och faktiska hjulfiler, som accepterar begränsade CPython 3.12/AArch64-taggar och verifierar SHA-256. Den skapar inga filer och hämtar eller installerar inga paket. Frånvaro av manifest betyder NO-GO. Även en korrekt hash- och taggkontroll betyder **inte** att native ABI eller resolverns fullständiga beroendeslutning verkligen verifierats. Testskriptets resultat har därför uttryckligen `dependency_closure_verified=false`, `native_abi_tested=false` och `audio_authorized=false`.

## Låsta 28 binära beroendeartefakter (2026-10-16)

På **GitHub-hostad x86 Linux** (inte VENTUNO) genomfördes en verklig
`pip download --only-binary=:all: --implementation cp --python-version 3.12
--abi cp312 --platform manylinux*_aarch64` med alla transitiva beroenden.
Upplösningen lyckades med **28** kompatibla wheel-artefakter, inklusive
`faster-whisper`, `sounddevice`, `webrtcvad-wheels`, `pyttsx3`,
`ctranslate2`, `av`, `numpy` och `onnxruntime`. Inget installerades,
modeller laddades inte och ingen mikrofon öppnades.

Version och faktiskt SHA-256 för vart och ett av dessa 28 filer är sparade i:

- `config/voice_arm64_cp312_wheels.lock.json` (filnamn, hash, målplattform).
- `requirements-voice-arm64-hashed.lock` (alla 28 exakta paketversioner
  inklusive `--hash=sha256:...`).

`scripts/ventuno_voice_static_lock_check.py` nekar om källans båda
incheckade listor divergerar; CI laddar på nytt från PyPI på **hosted**
till en **temporär** katalog med `--require-hashes` och jämför den
nedladdade hashmängden mot käll-låsningen innan temporär data raderas.
Detta är reproducerbar **paketupplösning på rätt hjultaggar**, men
**bevisar fortfarande inte att kod och native library ABI fungerar på
VENTUNO:s faktiska Ubuntu-/Qualcomm-installation**. Den aktiva produktionens
venv saknar dessa röstpaket tills en framtida separat, tillåten staging
har genomförts. All fysisk/in-process modellkörning är därför fortsatt NO-GO.

## Effektiva körinställningar och heartbeat

Den installerade startfilens bytes har verifierats mot den granskade filen och `MainPID` samt känd argv-form har verifierats. Det bevisar inte tidigare inlästa inställningar. För **framtida** instrumenterade versioner har `core/runtime_safety_attestation.py` tillförts: `MyAIRuntimeService.status()` bäddar in en mycket begränsad mängd härledda booleska riskflaggor och processidentitet i den lokala heartbeat som tjänsten redan skriver.

Den läsande kontrollen `scripts/ventuno_active_runtime_launch_readonly.py` kan, **om** sådan framtida heartbeat finns, kontrollera färskhetsgräns, överensstämmande PID och att enbart isolerade OFF-flaggor rapporteras. Råa filnamn, API-nycklar och hela processmiljön redovisas inte. Även då är en lokal heartbeat ett **samverkande processtillstånd**, inte kryptografisk fjärrattestation. Framför allt: **den redan körande VENTUNO-versionen har inte uppdaterats här och dess in-memory inställningar förblir obekräftade**.

## Återstående fysiska och operatörsstyrda spärrar

- Den fullt utrustade MyAI-röstsessionen är **NO-GO** tills versionslåsning, isolerad installation, ABI- och testprofil-verifiering är genomförda.
- En redan separat testad `arecord`/ALSA engångssekvens är en annan exekveringsväg; den får endast upprepas med färskt, uttryckligt fysiskt samtycke och efter aktuellt skrivskyddat USB-preflight.
- QNN/HTP på NPU får **inte** köras utan separat modellprofil, verifierad uppspelnings-/återställningsväg, processstopp, extern operatör och godkänd säkerhetsspärr. Ingen direkt operatorprofil/cykelmätning genomfördes här.
- Kända åtta syntetiskt testade `Popen`/`exec`-ställen får förbli synliga i static audit; de är inte automatiskt säkerhetscertifierade för nativa hjälp-processer.

### Loggpolicy

Körningar använder disponibla, exakta checkouter och endast källkodsanalyser på VENTUNO. Eventuell framtida wheelupplösning får ske **bara på GitHub-hostad Linux med temporär katalog**, aldrig med pip i aktiv produktions-venv; koden måste avsluta/rapportera NO-GO snarare än falla tillbaka till systempaket eller native build.
