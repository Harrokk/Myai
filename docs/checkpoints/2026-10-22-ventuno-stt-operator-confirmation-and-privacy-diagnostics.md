# MyAI – uppföljning efter det fysiska STT-misslyckandet (ingen ny inspelning)

**Datum:** 2026-10-22. **Utgångspunkt:** DRAFT PR #352, `079d5d201d85dd46ec671904388cd4b893cd13c9`, den enstaka fysiska inspelningen https://github.com/Harrokk/Myai/actions/runs/39811054182. **Status: enbart offline- och syntetiska tester.**

## Ny information från den fysiska operatören

Operatören bekräftade efter den fysiska försöksomgången att uppmaningen **"Säg: Vad heter du."** hördes och att hen svarade **"Vad heter du?"** direkt efteråt. Ingen upprepning eller ny fysisk inspelning har godkänts och **ingen sådan utfördes** i denna PR.

Den ursprungliga körningen visade `capture_signal_class=bounded-audio-level` samt `unmatched_category=unrelated-short-utterance`. Utifrån den befintliga koden betyder den senare kategorin att det normaliserade Whisper-resultatet bestod av **högst två ord**, inte att treordsfrågan `vad heter du` bara skilde sig med frågetecken, versal eller trivial interpunktion. Den kodvägen accepterar redan både `Vad heter du?` och `vad heter du` och exakta godkända vokativvarianter.

Utifrån dessa uppgifter är korrekt första arbetshypotes **ofullständig eller felaktig STT-avkodning, felinspelat tidsfönster, eller annan ljudkälla/noise i PCM**. Ingen av dessa orsaker är bevisad. Den av integritetsskäl raderade råa inspelningen och transkriptionen får inte återskapas eller härledas från framgångsloggarna.

## Pass 1 – granskat inspelningsförlopp

- `scripts/ventuno_usb_dialogue_hardware.py` kör den avgränsade svenska startsignalen innan `arecord` öppnar mikrofonen på `plughw:1,0`, `S16_LE`, 16 kHz, mono, tre sekunder, högst sju sekunders process-timeout.
- Capture verifierar exakt 96 000 PCM-bytes och returnerar data i minnet.
- `_limited_whisper_child` kör en isolerad, lokal Whisper Tiny-modell på CPU med `beam_size=1`, `best_of=1`, `language=sv`, `vad_filter=False` och `without_timestamps=True`; transkriptet överförs bara genom en privat subprocess-pipe och loggas inte.
- `OneShotUsbDialog` avvisar transkript som inte matchar den snäva, ofarliga svenska ordlistan. Då körs **ingen** lokal GenieX-fråga och **ingen** slutlig TTS.
- Det gamla globala PCM-måttet skiljde mellan tystnad, clipping och rimlig total amplitud men gav ingen antydan om **var i tresekundersfönstret energin låg**. En global RMS kan klassas `bounded-audio-level` även om väsentlig signal finns bara i en av tre delar.

## Pass 2 – ny strikt begränsad diagnos (ingen ny hårdvara)

`scripts/ventuno_usb_dialogue_once.py` får `classify_pcm_activity_layout(raw)`: delar endast **framtida** redan separat samtyckta 16-kHz/3s PCM i tre fasta delar, beräknar RMS per tredjedel i minnet och lämnar bara **en enda kort kategori**: `invalid-pcm`, `no-significant-activity`, `early-activity`, `middle-activity`, `late-activity` eller `distributed-activity`. Den lagrar inga samples, waveform, transkript, ord, tidsstämplar eller nivåvärden i resultatet; den härledda kategorin kan inte i sig identifiera tal, en talare eller orsaken till Whispers avkodning.

Kategorin läggs till i resultatet **endast om** det gamla engångsstyrda flödet faktiskt får ett PCM-klipp efter båda ljudgodkännandena. Ingen ny ljudöppning, modulnedladdning, retry, HTTP-fråga, talsyntes, automatisk transkriptacceptans eller ändring av någon högriskordlista läggs till.

`tests/test_ventuno_usb_dialogue_once.py` utökar med syntetiska, icke-språkliga konstanta PCM-värden i första, andra och sista sekunden och testar felaktiga PCM-data, integritetsgränser, avvisade tvåordsfraser som **inte** kontaktar GenieX, exakt engångskontroll och inget PCM-fält utan fullständigt ljudsamtycke.

### Negativa gränser

Denna klassificering **identifierar inte tal**: brus, hostning, högtalareko och andra ljud kan ge samma kategori som avsett tal. Det ursprungliga PCM-klippet är raderat, så den nya kategorin kan **inte** beräknas för testet den 22 oktober. Att köra samma fysiska workflow igen är förbjudet utan **nytt uttryckligt engångsgodkännande**.

**Nästa beslut efter hosted source-only CI:** använd synliga, rent syntetiska svenska testfraser för att jämföra Whisper Tiny och eventuellt Base och kontrollera om treordsprompten har återkommande misslyckanden. Om ännu ett fysiskt talförsök övervägs krävs ett nytt specificerat och användargodkänt engångstillfälle; följ då bara coarse energilayout, status och latenser samt behåll hård blockeringslista. Ingen automatisk justering till suddig/fuzzy frase-matchning, eftersom en felhörd högre risk-instruktion annars skulle kunna misstas för den ofarliga testfrågan.

**Produktion NO-GO, ingen main-merge och inga tjänsteändringar på VENTUNO.**
