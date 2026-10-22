# MyAI – source-only säkrare startuppmaning vid nästa explicita engångsrösttest

**Datum:** 2026-10-22. **Bas:** DRAFT PR #355, SHA `91cd76a142dc8e16c7d6ec699ba0bddef224a80a`.
**Status:** ändring av källkod och syntetiska regressionstester. **Ingen ny fysisk inspelning, ingen installation.**

## Granskat faktaunderlag

I den första riktiga tresekundersinspelningen bekräftade användaren att VENTUNO:s taluppmaning hördes och att svaret `Vad heter du?` kom **direkt efteråt**. Whisper Tiny avkodade ett annat, orelaterat kort transkript. Ingen slutlig AI-fråga eller TTS genomfördes. Rå PCM och transkript sparades inte.

Källkodens exakta sekvens i `scripts/ventuno_usb_dialogue_once.py` är: först `audible_start_cue()` som spelar färdigt välkomstuppmaningen, **därefter** `capture()` som startar en ny separat ALSA `arecord`-subprocess. Det finns därför en **ologgad, okänd** fördröjning mellan sista hörbara cue och ögonblicket inspelningen faktiskt börjar. Varken startfördröjningen eller en eventuell förlorad första stavelse mättes i det ursprungliga fysiska testet.

Den tidigare syntetiska körningen på hostad ARM64 (https://github.com/Harrokk/Myai/actions/runs/39824277348) gav **0 av 2** korrekta Piper-`Vad heter du?` när 700 ms av den fasta tresekunderssignalens början tystades. Det är en möjlig mekanism, **inte ett bevis** för exakt detta fel i fysisk mikrofon.

## Genomförd riskbegränsning

I `scripts/ventuno_usb_dialogue_hardware.py` är den syntetiserade och digitalt volymbegränsade startuppmaningen till ett **framtida** engångstest nu:

> Vänta en sekund. Säg sedan: Vad heter du.

Istället för tidigare `Säg: Vad heter du.`.

Detta ger användaren en tydlig muntlig anledning att **inte börja tala omedelbart efter cue**, vilket kan minska risken att första stavelsen går förlorad under uppstarten av `arecord`. Instruktionen **garanterar inte** att inspelningen påbörjats vid rätt tid: verklig `arecord`-startup och mänsklig svarstid är fortfarande omätta. Skulle problemet kvarstå efter en separat tillåten fysisk testomgång krävs ny design med tydlig readiness-signal; vi får inte bara öppna mikrofonen i bakgrunden utan samtycke.

Den låsta tresekunders-PCM-storleken, ASR-modellen, igenkänningskravet, 4 %-begränsningen på utljudet, integritetsskyddet och stopp-vid-fel är oförändrade. Det tidigare engångsgodkännandet återanvänds **inte**.

`classify_unapproved_question()` klassificerar nu både den gamla cue-frasen och den nya längre cue-frasen som `spoken-cue-echo-suspected` om ASR tolkar uppspelat uppmaningsljud, och avvisar den som användarfråga. Detta förändrar inte tillåtna kommandon, ger ingen automatisk fuzzy-godkänning och vidarebefordrar aldrig cue-text till GenieX.

Regressionstesterna kontrollerar exakt den nya uppmaningen, att en gammal felaktig eller ny cue-echo inte når AI-modellen eller slutlig ljuduppspelning, samt att det inte går att spela in utan bägge separata ljudgodkännanden och att ett andra försök alltid nekas.

## Gräns mot verkligt test

Den här ändringen byggs och testas **endast på GitHub-hostad ARM64**. Den får inte automatiskt köras på fysisk VENTUNO, installeras som aktiv tjänst eller aktivera en andra inspelning. Den framtida engångsinspelningen kräver åter ett **nytt, uttryckligt, tidsavgränsat och konkret användargodkännande**, fysisk närvaro, kontroll av aktuell USB-enhet samt en tydlig stop-möjlighet. Anpassa då ett nytt rent test-workflow till den nya exakt granskade test-SHA:n. Ändra aldrig gamla engångsworkflows till återspelbara ljudtester.

**Produktionsstatus: NO-GO.** Runner-UID/ACL och skydd mot GitHub-workflowhistorik återstår. Ingen merge till `main`, inga NPU- eller hårdvarukörningar i denna PR.
