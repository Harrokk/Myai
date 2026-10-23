# MyAI – identisk fysisk Whisper-process med syntetiskt Piper-ljud

**Datum 2026-10-23. Bas:** DRAFT PR #358, HEAD `8c195cbae582a9fa3fb1d4a9c970be68eb46851f`. **Status:** endast GitHub-hostad ARM64; INGEN ny mikrofon eller VENTUNO-inspelning.

## Fastställda observationer

Operatören bekräftade uttryckligen att VENTUNO:s nya uppmaning hördes, att hen **väntade omkring en sekund** och sedan sade `Vad heter du?`. Verklig körning https://github.com/Harrokk/Myai/actions/runs/39921612897 visade godkänd capture-nivå, `middle-activity`, men avvisat Whisper-resultat i kategorin `other-unmatched-utterance`. Utan sparat PCM eller ordagrant transkript finns inget tekniskt stöd för att påstå att frasen kom för tidigt, att ljudet var brusigt, att ett visst ord saknades eller att mikrofonen spelade in fel källa.

## Granskningspass 1 – arbetsflödet till Whisper

`scripts/ventuno_usb_dialogue_hardware.py` kör faktiskt `arecord` med `plughw:1,0`, `S16_LE`, **16000 samples/s, mono, tre sekunder**, exakt **96000 bytes** till stdout. `_PRIVATE_WHISPER` läser 96001 bytes och kräver exakt 96000, konverterar med `np.frombuffer(..., dtype="<i2").astype(np.float32)/32768.0` och laddar SHA256-kontrollerad Tiny-int8 på CPU med `language="sv"`, `beam_size=1`, `best_of=1`, `vad_filter=False`, `without_timestamps=True`, `no_speech_threshold=0.6`, `condition_on_previous_text=False`. Dessa val och formatet ligger i stort sett i linje med tidigare benchmark-processen; någon konkret och verifierad byteordnings-/PCM-typbugg hittades **inte** i detta pass.

Men våra tidigare syntetiska Piper-studier använde **benchmarkkoden `_INFERENCE`**, inte just det `_PRIVATE_WHISPER`-program som kördes vid båda fysiska misslyckandena. Trots nästan identiska parametrar bör det bedömas med den exakta verkliga programvägen före nästa inspelning.

## Granskningspass 2 – nytt offline-test

`scripts/ventuno_exact_physical_stt_decoder_synthetic.py` kör **samma befintliga `_limited_whisper_child` och `_PRIVATE_WHISPER`** från den fysiska drivrutinen, och skickar bara fixerade Piper Alma-modellens `Vad heter du?` (pinnad modell) som tresekunders S16_LE i privat stdin. Kontrollen lägger till nominellt 12 dB syntetiskt brus, nominellt 0 dB syntetiskt brus och en deterministisk bortklippning av de första 700 ms. Alla fyra ljudvarianter finns endast i RAM och används på GitHub-hostad ARM64, aldrig i en mikrofon.

Resultatfält är begränsade till fyra klassificeringar: `accepted_exact_harmless_question` (boolesk), redan allowlistade kategorier, grov energiplacering och variantnamn. **Inga avkodade ord, privat ljud, ljudfil, transkript, WAV eller hash av transkriptet** skrivs ut. Avkodningen anropar exakt samma isolerade enbarnsprocess och riskgrind som fysiskt används och tillåter inte fler kommandon eller körning av GenieX.

`tests/test_ventuno_exact_physical_stt_decoder_synthetic.py` testar lyckade/avvisade fall med konstgjorda PCM-samples och transkript, inklusive självuppspelad cue som aldrig får tolkas som användarfråga. De verifierar att rå transkripttext aldrig återkommer i utskriftsstruktur och att varken inspelning eller fysisk uppspelning kan aktiveras utan separat tillstånd.

`.github/workflows/hosted-exact-physical-whisper-synthetic.yml` är en ny, unik workflow-fil som kör **endast github-hosted `ubuntu-24.04-arm`**, exakt source-SHA och det sedan tidigare fungerande pinnade temporary Piper/Whisper-stagingflödet. Den använder aldrig `self-hosted` eller `ventuno-q`.

## Begränsningar och nästa tillståndsgrind

Detta experiment jämför en känd syntetisk signal med **exakt fysisk avkodarkod**, men mäter inte mikrofonens brus, kortets ALSA-buffring, mikrofonplacering, faktisk ljudstyrka eller Whisper Tiny:s tolkning av operatörens verkliga tal. Om syntetiskt original går igenom och verkligt tal fortsätter att misslyckas finns ett tydligare motiv för separat auktoriserad mätning av den fysiska ljudkedjan, men ingen rätt att göra den automatiskt.

**Tidigare ljudsamtycke är förbrukat. Inget nytt `arecord`, `aplay`, NPU, tjänsteändring, `main`-merge eller produktionsdeployment tillåts.** Det gamla fysiska jobbet ska inte köras igen.

En fullständig hosted ARM64-projektsvit och den separata faktiska hosted Piper→produktion-avkodaren måste köras och verifieras på **exakt slutlig PR-HEAD** innan resultat redovisas som bekräftat. Produktion NO-GO.
