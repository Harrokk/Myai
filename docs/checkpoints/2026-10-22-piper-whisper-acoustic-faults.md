# MyAI – Piper/Whisper Tiny: syntetisk störnings- och ekoanalys

**Datum:** 22 oktober 2026. **Bas:** DRAFT PR #354, SHA `3f6ce25c8a8a1812ad1958cd4405c5de6d6a6e8f`. **Status:** endast GitHub-hostad ARM64; ingen fysisk VENTUNO-inspelning.

## Faktiskt verifierad baslinje från PR #354

Fullständig GitHub-hostad ARM64-projektsvit **4 278 passed, 7 skipped** https://github.com/Harrokk/Myai/actions/runs/39814990241. För separat syntetisk Piper Alma → Whisper Tiny-körning https://github.com/Harrokk/Myai/actions/runs/39814990139 var **alla 8 av 8** exakta `Vad heter du?` (fyra PCM-varianter × beam 1/5), inferenslatens 0,40–0,45 sekunder på den hostade runnern. Det är inte uppmätt VENTUNO-latens. Normal 3s PCM, tal -250ms tidigare, +400ms senare och 25 % digital amplitud gav samtliga rätt. Det tidigare verkliga ljudförsöket var ändå `reject-unapproved-or-unclear-test-utterance`, vilket dessa fyra rent digitala manipulationer INTE förklarar.

## Nya syntetiska undersökningar (ingen verklig användarröst)

`scripts/ventuno_stt_synthetic_window_robustness.py` utvidgar samma pinnade Piper Alma/Whisper Tiny-fixture med fyra reproducerbara varianter:

| Variant | Endast syntetisk manipulation | Undersöker |
|---|---|---|
| `noise_snr_12db` | Pseudobrus med fast seed, ungefär 12 dB nominell SNR | måttligt bakgrundsbrus |
| `noise_snr_0db` | Pseudobrus med fast seed, ungefär 0 dB nominell SNR | kraftigt maskerat tal |
| `echo_180ms` | fördröjd kopia 180 ms och nivå 35 % | förenklad efterklang/eko |
| `onset_muted_700ms` | nollställ första 700 ms i PCM-fönstret | borttappad början av talet |

Samtliga har fasta gränser, `16kHz/mono/S16_LE`, tre sekunder och exakt 96 000 bytes; behandlas endast i minnet. Originalets fyra jämförelsepunkter bibehålls. Totalt åtta ljudvarianter × två avkodningsparametrar ger **16 syntetiska resultat**. Nya testmätningar kan skilja sig från de tidigare av miljöskäl.

Testskriptet använder **samma signerade/pinnade, filstorlekskontrollerade modellen** som den redan verifierade testsviten. Inga användar- eller mikrofondata läses, inget transkript loggas, inga PCM-/WAV-filer sparas och inga resultat behandlas som nya tillåtna MyAI-kommandon. Resultatet visar bara exakt frasträff, treordsöverlapp, grova avståndsband, ungefärlig inference-svarstid och grov energifördelning. Det är inte en mätning av fysisk mikrofonkaraktäristik, en verklig ekoalgoritm eller verklig omgivningsakustik. `scripts.ventuno_usb_dialogue_once` och verklig kommandogrind lämnas oförändrade.

`tests/test_ventuno_stt_synthetic_window_robustness.py` täcker att manipulationerna är deterministiska, att högre brusstyrka ger större förändring, att 180 ms echo är fördröjt, att exakt den första 700ms av nollas ut, att PCM-formatet bevaras och att osäkra/okända indata avvisas utan att en fysisk enhet öppnas.

`.github/workflows/hosted-piper-whisper-acoustic-faults.yml` använder **bara** GitHub-hostad ARM64 och separat temporär modell- och venv-installation med kända checksummevärden. Den använder aldrig `self-hosted` eller `ventuno-q`. Workflow-filens branchspecifika trigger hindrar oavsiktligt nytt fysiskt ljudjobb.

## Tolkning och fortsatt NO-GO

Vi bör inte automatiskt dra slutsatsen att ljudproblem beror på eko, vare sig ovanstående tester misslyckas eller lyckas. Det enda tidigare fysiska testklippet och transkriptet är avsiktligt borta; varken jämförelsen eller nya syntetiska prover kan återskapa dess orsak. Användaren måste uttryckligen tillåta **en ny konkret inspelning** innan något ytterligare fysiskt rösttest planeras. Ingen försämring av säkerhetsgrinden för exakta ofarliga svenska kommandon, ingen ändring av produktions-STT, ingen installation på VENTUNO eller merge till `main`.

**Acceptans:** exakt sista SHA måste klara både fullständig GitHub-hostad ARM64-suite och separata verkliga modellinferensen i tillfällig miljö. Misslyckad frasklassificering i en av de avsiktligt brusade syntetiska varianterna ska synas som diagnos, inte gömmas och inte klassificeras som kodtestfel.
