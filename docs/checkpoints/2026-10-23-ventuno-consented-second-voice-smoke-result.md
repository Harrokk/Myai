# MyAI VENTUNO Q – andra uttryckligen godkända fysiska röst-smoke-testet

**Datum:** 23 oktober 2026, faktisk hårdvarukörning ca **08:02 UTC / 10:02 svensk sommartid**.
**Status:** **PARTIAL / STT REJECT**, avsiktligt stopp före LLM och avslutande TTS. **Ingen ny ljudinspelning tillåten utan nytt uttryckligt engångsgodkännande.**

## Samtycke och låst version

Användaren bekräftade uttryckligen **fysisk närvaro vid VENTUNO Q** och gav tillstånd till **ett** övervakat test: en kort ljuduppmaning med låg volym, exakt en tresekunders mikrofoninspelning, en ofarlig fråga via lokal GenieX och ett kort lågvolymsvar **endast om** Whisper först verifierar frågan. Inget nytt tillstånd för repetition eller kontinuerlig lyssning lämnades.

- **Fryst källkod:** `029679ea5e10a97e867aa1db6e09bc3bcdeac3d1` (DRAFT PR #357), verifierad före fysiskt test med GitHub-hostad ARM64 full svit **4302 passed, 7 skipped** och faktiska eSpeak-längdtest **3,041 s**.
- **Engångsorkestreringscommit:** `4869e4dd64b36bbb47944d01acfb360184959dcf`, endast workflowfil på unik gren `dev/ventuno-consented-cue-smoke-20261023`.
- **Verkligt fysiskt GitHub Actions-jobb:** https://github.com/Harrokk/Myai/actions/runs/39921612897 – runner **`ventuno-q`**, runner-jobb `120307932654`. Jobbet **failure** eftersom den fail-closed STT-grinden korrekt avslutade med exit 2. Detta är inte ett godkänt fullständigt röstsmoke-test.
- Workflow är endast `push` på exakt ovanstående unika gren och exakt filpath; jobbvillkor `github.run_attempt == 1` och unikt meddelande `Authorize single new-cue 3s USB dialogue on VENTUNO Q 2026-10-23`. **Använd inte Rerun.** Kodens `OneShotUsbDialog` har intern `_used` som ytterligare processlokalt skydd; sammanhanget gäller ändå enbart detta enda körda workflow.

## Fysiskt observerade fakta

1. Testet hämtade den frysta koden via ren `git checkout --detach` till en ny temporär privat katalog; ingen produktionsfil skrevs över.
2. **136 syntetiska USB-/röst-/drivrutinssäkerhetstester passerade** på den fysiska runnern.
3. USB/installerad säker röstprofil, MyAI/GenieX-tjänster, RAM och disk var redo före ljud; `ram_available_mib=13849` och `disk_available_mib=28967`. Final-readiness `ready-for-separate-consented-dialogue-test`.
4. Tillfälliga Whisper-wheels, verifierad Whisper Tiny CPU-modell och offline svensk eSpeak-källa godkändes.
5. **Särskilt nytt verkligt metadata-test på VENTUNO före ljud:** aktuell staged eSpeak-syntes av `Vänta en sekund. Säg: Vad heter du.` till RAM gav `cue_seconds=3.041` och efter `quiet_wav_from_tts` `safe_digital_peak_fraction=0.039978`, under gränserna 3,5 s respektive 4 % digital toppnivå. Det bevisar *digital* nivåbegränsning, inte det mänskliga ljudtrycket (SPL).
6. Endast en enhetlig tresekunders USB PCM-capture försöktes: `recording_attempted=true`; `capture_signal_class=bounded-audio-level`, `capture_activity_layout=middle-activity`. Mellandelsaktivitet är grovt energimått, **inte** bevis att alla tre ord överfördes eller att ljudet verkligen kom från användaren.
7. **STT gav inte ett godkänt kommando:** `status=reject-unapproved-or-unclear-test-utterance`, `unmatched_category=other-unmatched-utterance`, `transcription_verified=false`. Den privata råa transkriptionen och PCM kasserades som avsett. Kategorien innebär inte att exakt vilka ord eller varför Whisper misslyckades går att återskapa.
8. Därför `local_geniex_answer_verified=false`, `swedish_tts_verified=false` (gäller *slutligt AI-svar*), `playback_attempted=false`, `playback_completed=false`; inledande lågvolymcue skickades separat före capture och lyckades via ALSA.
9. `microphone_audio_saved=false`, `microphone_audio_transmitted=false`, `transcript_logged=false`, `geniex_reply_logged=false`, `generated_wav_saved=false`, `production_changed=false`, `repeat_attempt_allowed=false`.
10. `if: always()`-städningssteget kontrollerade MyAI och GenieX fortsatt `active` och tog bort den isolerade testkatalogen. Ingen `systemctl restart/stop`, ingen `main`-merge och ingen installation utfördes.

## Samlad diagnos och begränsningar

Första fysiska röstförsöket den 22 oktober (https://github.com/Harrokk/Myai/actions/runs/39811054182) hade `bounded-audio-level` men `unrelated-short-utterance`. Den 23 oktober ger en förbättrad ensekunds-vänta-uppmaning `middle-activity` och `other-unmatched-utterance`, dvs. felet har **inte** kunnat lösas med att enbart förlänga användarens väntan. Skillnaden i felkategori bevisar inte att STT-felorsaken ändrats; privata transkript saknas.

Innan nästa fysiska inspelning är det relevant att fråga operatören om hen hörde exakt den nya uppmaningen, verkligen väntade ungefär en sekund och svarade med `Vad heter du?`. Därefter bör ett *helt syntetiskt/offline* test kunna undersöka bland annat mikrofonens typiska samplingsnivå, ALSA-startlatens, talsyntes-eko och om Whisper Tiny förväxlar flera korta svenska fraser. Inga släpp på `approved_short_question` och ingen fuzzy wildcard-kommandotolkning tillåten.

Detta är **NO-GO** för automatisk röstlyssning, live deployment, privilegierad runner-migrering och produktionsnyckelrotation. GitHub-runnerns äldre behörighet/UID/ACL-produktionsrisk är fortfarande öppen. Endast detta uttryckligen godkända engångstestet genomfördes.
