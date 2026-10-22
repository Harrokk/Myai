# MyAI – svensk syntetisk STT robusthet för mikrofonfönster (endast hostad testmiljö)

**Datum 2026-10-22. Bas:** DRAFT PR #353, HEAD `e3a371a98662dd3b3a50bebe01d9071d7ab2ba5b`.

## Utgångsläge och tidigare faktiska mätningar

De gamla verifierade körningarna på den fysiska VENTUNO Q är redan klara och behöver **inte upprepas**:

- eSpeak NG på samma fras `Vad heter du?`, Whisper Tiny/Base med beam 1/5 och två talhastigheter: **0 av 8 exakta träffar**. https://github.com/Harrokk/Myai/actions/runs/38282373164
- En tidigare finare avståndsanalys visade högst **ett av tre** mål-ord i varje resultat, inte en interpunktionsfråga. https://github.com/Harrokk/Myai/actions/runs/38283378612
- Den syntetiska svenska rösten **Piper Alma medium** på samma fras, motsvarande Tiny/Base och beams: **8 av 8 exakta träffar**. https://github.com/Harrokk/Myai/actions/runs/38284679674

Detta stödjer att kvaliteten på det syntetiska inmatningsljudet har stor betydelse, men bevisar **inte** var felet fanns i operatörens verkliga ljud från 22 oktober 2026. Operatören har bekräftat att uppmaningen hördes och att `Vad heter du?` sades direkt efteråt. Klippet och Whispers privata transkript raderades som avsett.

## Steg 1: kontrollerad syntetisk tid-/nivåmodell

`scripts/ventuno_stt_synthetic_window_robustness.py` använder **bara** den fixerade Piper Alma-rösten, verifierad med hårdkodad SHA-256 och fysiskt tidigare prövad Tiny-Whisper-modell (också SHA-256-pinnad). Ingen del kan öppna mikrofon eller ljudhögtalare.

En enda engångsrendering av `Vad heter du?` i privat RAM omvandlas till samma 3 sekunder / 16 kHz / mono / S16_LE som tidigare hårdvaruförsök. Fyra deterministiska varianter skickas sedan **två åt gången** genom den redan säkerhetsgranskade isolerade Tiny-CPU-Whisper-koden med beam 1 och beam 5:

| Variant | Ändring | Fråga |
|---|---|---|
| `reference` | Ursprunglig Piper PCM, 350 ms ledande tystnad | Fungerar baslinjen även i detta experiment? |
| `early_250ms` | Flytta digitalt tal 250 ms tidigare med nollfyllnad | Kan tidig inspelning ge annan avkodning? |
| `late_400ms` | Flytta digitalt tal 400 ms senare med nollfyllnad | Kan sen insignal ge annan avkodning? |
| `gain_25pct` | Exakt 25 % digital ljudamplitud | Kan låg ljudnivå påverka avkodningen? |

Den privata child-processen använder samma lokala CPU-int8-modell, svenska, `beam_size`, `no_speech_threshold` och **ingen** `initial_prompt` som tidigare. Resultatet begränsas till exakta boolska frasträffar, klippta avståndsband och ordöverlapp (0–3), ungefärlig inferenstid och grov tresekunders aktivitetskategori. Inget tal, ljud, WAV eller transkript lagras eller loggas.

**Kritisk tolkningsbegränsning:** digitalt tidsskiftad Piper är inte en riktig mikrofon – brus, gain control, eko, ljudingångens faktiska latens, personens uttal och ljudkortets hela akustiska kedja saknas. Ett matchningsresultat visar bara Tiny på just detta syntetiska ljud. Ändra inte MyAI:s produktions-STT eller dess exakta kommandogränser automatiskt.

## Steg 2: fullständig GitHub-hostad ARM64-inferens och test

`.github/workflows/hosted-piper-whisper-window-robustness.yml` kör **enbart på `ubuntu-24.04-arm` med `runner.environment=github-hosted`**, exakt commit i separat scratch, snävt begränsat read-only GitHub-token, isolerat faster-whisper-venv och Piper-venv. Piper-ARM64-wheelens exakta SHA-256 och Whisper-/Piper-modellernas SHA-256 måste matcha innan något CPU-test sker. Värden, ljud och modeller avlägsnas från scratch efteråt.

`tests/test_ventuno_stt_synthetic_window_robustness.py` testar syntetiska shift-index, nollfyllning, låg gain, ogiltiga ramar, nej till inferens utan explicit syntetiskt testval och gränsen mot ljud-/modell- och produktionsfunktioner. Den vanliga fullständiga ARM64-source-only-sviten körs automatiskt separat på samma commit.

**Alla riktiga mätresultat måste hämtas från faktiska godkända jobb; inga siffror för detta nya experiment får påstås innan dess.** Även om hela CI blir grönt gäller **NO-GO för fysisk ny ljudinspelning utan nytt användargodkännande** och **NO-GO för självutvecklingspromotion/produktion**.
