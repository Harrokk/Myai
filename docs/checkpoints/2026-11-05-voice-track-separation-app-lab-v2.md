# MyAI röstspår: arkiv och App Lab ASR v2 — 2026-11-05

## Separationsbeslut

Användaren har beslutat att sluta fortsätta med egna Whisper Tiny-/ALSA-inspelningsexperiment som huvudsaklig väg och i stället gå vidare med Arduinos App Lab ASR och färdiga röstfunktioner på VENTUNO Q.

Det befintliga, fullt åtkomliga utvecklingsläget från DRAFT PR #403 bevaras under **Git-grenen `archive/legacy-voice-20261105`**, exakt commit `8b3409c1b5e3965edc2f10742e26b39cc24eb6e8`. Det inkluderar tidigare ljud-, STT-, säkerhets-, CI- och checkpoint-arbete. Archive-grenen ska lämnas orörd. PR #400–403 finns kvar som DRAFT och får inte automatiskt slås samman.

**Ny isolerad gren:** `dev/app-lab-asr-v2-isolated-20261105`, som startar från samma granskade commit men bara lägger till filer i `integrations/arduino_app_lab/asr_v2/`, separat test och denna dokumentation. Gamla filer flyttas eller tas inte bort eftersom deras importberoenden och tester ännu inte är kartlagda för en säker fysisk flytt. *Git-gren och namnrymd är logisk separation, inte en garanti för konfliktsäker framtida merge.*

## Kodgräns och förbud

- `integrations/arduino_app_lab/asr_v2/` är den enda platsen för nya App Lab ASR v2-koddelar.
- Den nya koden får inte importera `core/`, `modules/`, `scripts/`, historiska USB/Whisper-adaptrar, ALSA, Ollama, GenieX, Arduino SDK eller verktygs-/process-API:er. Source-only CI kontrollerar importgränsen.
- `track.json` är en **deklarativ, uttryckligen AVSTÄNGD** profil, och `check_disabled_track_config` avvisar varje försök att aktivera antingen det gamla spåret, inspelning, LLM, verktygsdispatch eller tjänstekontroll via denna profil.
- `FinalTextOneShotGate` accepterar endast redan externt levererad `full_text` efter en explicit UI-händelse. Den kan varken spela in, avkoda, ladda modell, använda internet eller utföra kommando.
- Aktiva `config/profiles/ventuno_q.json` ändras **inte**; `voice.enabled`, `tts_enabled` och `handsfree_enabled` förblir AV.
- För framtida fysiska App Lab-steg krävs en separat operatorstyrd installation, kontrollerat ljudsystem och särskilt godkännande innan capture eller tjänstestopp. Inga historiska samtycken återanvänds.

## Nästa planerade steg

1. Verifiera Arduinos befintliga App Lab ASR-moduls API och tillgång på den faktiska VENTUNO-installationen (först läsande metadata).
2. Granska mic-ljudkedjans färdiga nivå/AGC/VAD/noise-suppression, endast aktivera det som stöds.
3. Bygg separat testad adapter från officiell ASR `full_text` till MyAI:s *read-only* kärna; explicit datagräns, ingen verktygskörning.
4. Anslut TTS som en oberoende, separat auktoriserad etapp efter STT.
5. När koden och reella tester är färdiga: granska en liten, kontrollerad migrering. Gör ingen merge/deploy förrän dess.

## Test och status

Ny gren avsiktligt source-only; GitHub-hostade tester får köras, aldrig VENTUNO self-hosted, mikrofon, tjänsteförändring eller modellinstallation. Tidigare DRAFT-resultat var inte en release och ingen produktionsändring är gjord.
