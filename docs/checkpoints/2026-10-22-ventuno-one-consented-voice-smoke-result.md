# MyAI – första engångsgodkända fysiska röstsamtalet 2026-10-22

**Fysisk maskin:** VENTUNO Q, runner `ventuno-q` ARM64.
**Testets datum/tid:** 2026-10-22 16:07 UTC / 18:07 svensk sommartid.
**Låst testkälla:** `d28165c1cad81f8b4308ac7355a3fdfd81334986` (DRAFT #349).
**Instrumenteringsworkflow SHA:** `0896b61375840df8f260b8bda90c065d24a2be67`.
**Fysisk Actions-körning:** https://github.com/Harrokk/Myai/actions/runs/39811054182, jobb `119937074481`.

## Engångsgodkännande

Användaren uttryckligen bekräftade att hen är vid VENTUNO och att exakt en kort inspelning och låg uppspelningsvolym är godkända. Arbetsflödet aktiverades en gång via unik branch/commit, med `github.run_attempt == 1` och helt unik commit-message. **Samtycket är förbrukat**, ingen automatisk retry eller workflow-rerun med mikrofon är tillåten.

## Faktiskt resultat

- Exakt frusen source-SHA verifierad med ren checkout under tillfällig katalog; inga produktionskällfiler ersatta.
- Mockade röst-/USB-/säkerhetstester godkändes på den fysiska runnern.
- USB capture + playback, tjänster, 8 GiB ledigt RAM och temporärt lagringsutrymme godkända före inspelningssteg.
- Isolerade ARM64 Whisper-bibliotek, svensk ljudreferens och pinned Whisper Tiny CPU-prov godkändes.
- Svenska eSpeak-syntesen verifierades i temporär testmiljö.
- Sista fysiska readiness var `ready-for-separate-consented-dialogue-test`.
- En enda signerad lågvolym-startuppmaning `Säg: Vad heter du.` kördes före tresekunders mikrofoninspelningen.
- Sanitiserad körstatus `recording_attempted=true`, `capture_signal_class=bounded-audio-level`.
- **Taligenkänningsresultatet avvisades:** `status=reject-unapproved-or-unclear-test-utterance`, `unmatched_category=unrelated-short-utterance`, `transcription_verified=false`.
- Därmed `local_geniex_answer_verified=false`, `playback_attempted=false`, `playback_completed=false` för AI-svaret.
- `microphone_audio_saved=false`, `microphone_audio_transmitted=false`, `transcript_logged=false`, `geniex_reply_logged=false`, `generated_wav_saved=false`, `production_changed=false`, `repeat_attempt_allowed=false`.
- Slutlig fysiskt jobb **failure (avsiktlig fail-closed kontroll), exit 2**; separat städningssteg lyckades. Både `myai-geniex.service` och `myai-ventuno.service` kontrollerades fortsatt aktiva, hela tillfälliga röstarbetskatalogen borttagen.

## Vad testet bevisar och INTE bevisar

USB-mikrofonen gav en tillräckligt stark verklig insignal och säkerhetskedjan försökte tolka det korta ljudet med Whisper. Startcue skickades till ALSA och det fysiska kommandot returnerade lyckat. Men **vi har inte kunnat verifiera vad användaren faktiskt hörde eller sade**; loggarna innehåller avsiktligt inga transkript eller rå PCM. Resultatet visar därför **inte** vilken svensk fras som talades eller varför Whisper avvisade den. Det är inte ett fullständigt genomfört lokal AI-dialogtest. Inget GenieX-chatsvar och ingen slutlig AI-uppläsning provades.

När användaren kan bekräfta om startuppmaningen hördes och om `Vad heter du?` sades inom inspelningsfönstret får nästa diagnos göras. Detta bör i första hand ske via **källkodsgranskning av tidsfönster, gain, enhetstyp och Whisper-aliaser**, inte via ännu en inspelning. Ny verklig ljudinspelning kräver **ny uttrycklig engångsauktorisation** och samma eller ny granskad låst source-SHA.

## Säkerhetsstatus

- Ingen `main`-merge eller aktivering av självmodifierande MyAI.
- Inga aktiva produktionsinställningar eller systemd-enheter ändrade.
- GitHub-runnerns verkliga UID-/ACL-isolering och historiska workflowåtkomster ännu blockerade för produktionsgodkännande.
- Ingen ny NPU/HTP-inferens och inga stresstester.
- **Hårdvarusteg 1 PASS; röst-smoke-test delvis godkänt, STT-gate FAIL; produktion NO-GO.**
