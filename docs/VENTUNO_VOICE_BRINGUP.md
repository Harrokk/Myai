# MyAI VENTUNO Q – verklig röstfunktion, etappvis inkoppling

**Status 2026-10-12:** Förberett, inte aktiverat. MyAI, GenieX och den
befintliga tjänsteinstallationen får inte startas om, omkonfigureras
eller få extra STT-/LLM-modeller laddade bara för att köra ett CI-test.

## Verifierad fysisk ljudinventering

En skrivskyddad kontroll av VENTUNO Q rapporterade:

| Kontroll | Utfall |
| --- | --- |
| ALSA-ljudkort | 1 |
| Fysisk Linux-enhetsnod för PCM-inspelning | 1 |
| Enhetsnoder för PCM-uppspelning | 2 |
| ALSA-kontrollnod | 1 |
| `sounddevice`, `webrtcvad`, `faster_whisper`, `pyttsx3` | Inget av paketen kunde hittas i den aktiva MyAI-venv |
| VENTUNO-profilens `voice.enabled`, `tts_enabled`, `handsfree_enabled` | Samtliga `false` |

Diagnostik: https://github.com/Harrokk/Myai/actions/runs/38230247201

**Enhetsnoder bevisar inte att mikrofonen tar emot användbar signal**
eller att ljudutgången kan återge tal. Det finns ännu ingen verklig
inspelnings-/uppspelningstestlogg.

## Säker inkopplingsordning

### 1. Inventering – slutförd

Kör enbart read-only (inga mikrofonljud eller andra API-anrop):

```bash
python3 scripts/ventuno_voice_readiness.py
python3 scripts/ventuno_microphone_smoke.py
```

Det senare kommandot visar bara om ALSA-verktyget `arecord` finns,
**utan att spela in något**.

### 2. Tvåsekunders mikrofontest – kräver uttryckligt godkännande

Efter att användaren uttryckligen godkänt inspelning, om `arecord` är
installerat, kan en separat fysisk testkörning startas:

```bash
python3 scripts/ventuno_microphone_smoke.py \
  --record-2s --consent-to-record
```

Testet använder 16 kHz mono S16_LE i två sekunder och redovisar endast
RMS, peak, bytes och antal sampel. Ljuddata hålls enbart tillfälligt
i processminnet och visas eller sparas inte. Det skickas inte till
fjärrtjänster eller STT. Det kan behövas fungerande rättigheter till
ALSAs inspelningsenhet samt en inkopplad, fungerande mikrofon.

Förväntad storlek: 64 000 byte. En läsbar enhetsnod räcker inte: en
påtagligt låg signalnivå eller ofullständigt resultat ger **inte**
en godkänd inspelningsfunktion.

### 3. Röstberoenden – inte installerade automatiskt

Installera inte `requirements-voice.txt` direkt i den aktiva
`/home/arduino/MyAI/.venv` som en del av CI. Granska istället först:

- tillgängligt RAM och lagring vid pågående Qwen3-4B/GenieX-inferens
- Python- och ARM64-wheel-kompatibilitet för `faster-whisper`,
  `sounddevice`, `webrtcvad-wheels` och `pyttsx3`
- PortAudio och talsyntesmotorns Linux-beroenden
- om STT-modellens viktfiler finns lokalt, och kostnaden för att hämta
  dem i en isolerad testmiljö
- mikrofon-/högtalarrouting och enhetsbehörigheter.

Installera/testa först med isolerad venv eller dokumenterat staging-förfarande.
Aktivera därefter en komponent i taget. Kör inte en extra stor modell
samtidigt som Qwen3-4B laddas.

### 4. Verklig end-to-end-kedja – ej körd

Uttryckliga separata kontroller krävs för:

1. Fysisk mikrofon: kort svensk inspelning med godkänt samtycke.
2. VAD: identifiera tal och tystnad utan falska triggers.
3. STT: svenska fraser transkriberas lokalt, mät latency och minne.
4. Resursöverlämning: STT:s minne frigörs före GenieX-anrop.
5. MyAI + GenieX: befintligt modell-API besvarar en transkriberad fråga.
6. TTS: svar spelas faktiskt upp på avsedd högtalare.
7. Handsfree, avbrott och eko-skydd: verifiera riktiga högtalare och mikrofoner.
8. Långtidstest: samtal över upprepade cykler, utan RAM-läckor eller
   oavsiktlig tjänsteåterstart.

## Säkerhetsgräns

Dessa read-only/opt-in-skript får **inte**:

- ändra `config/profiles/ventuno_q.json` eller aktivera voice automatiskt
- spela in ljud vid vanlig GitHub Actions-diagnostik
- ändra systemd, starta om GenieX eller lägga till nya modeller i dess cache
- öppna STM32 Router, sända ljud till externa tjänster eller slå på kamera.

Vid **godkänd** mikrofon- och beroendekontroll kan en separat
driftsättningsplan för `voice.enabled`, `tts_enabled` och
`handsfree_enabled` tas fram med rollback. Fram till dess är MyAI:s
röstfunktion säkerhetsmässigt **avstängd**.

## Isolerad ARM64-röststaging verifierad (2026-10-12)

**Detta ändrar inte den aktiva MyAI-installationen.** På VENTUNO Q har
ett separat, kortlivat Python-venv skapats i GitHub-runners temporära
katalog. Hela miljön och tillfälliga OS-paket togs bort i ett
alltid-kört rensningssteg efteråt. MyAI/GenieX-tjänsterna var aktiva
före och efter testet, och produktionsprofilens röstflaggor förblev
avstängda.

Resursmätning före staging:

- Tillgängligt RAM, `MemAvailable`: cirka **13,2 GB**.
- Tillgänglig lagring: cirka **34 GB**.
- Begränsningar: minst 1,5 GB RAM- och lagringsmarginal krävs för staging.
- Detta är ett **ögonblicksvärde**, inte ett långtidstest av
  samtidig Whisper-/Qwen3-exekvering eller Peak-RSS.

Faktiska tester av *installerbara ARM64-wheels*:

| Komponent | Separat venv | Importstatus |
| --- | --- | --- |
| `webrtcvad-wheels` / `webrtcvad` | Installerat | **Godkänd** |
| `pyttsx3` | Installerat | **Godkänd** |
| `sounddevice` | Installerat | Kräver PortAudio på denna Linux-installation |
| Distributionens `libportaudio2` | Endast nedladdat och uppackat i tmp | Ytterligare `libjack.so.0` saknades |
| Distributionens `libjack-jackd2-0` | Endast nedladdat och uppackat i tmp | **Godkänd `sounddevice`-import** med båda lokala biblioteken |

**Alla tre lätta rösters Python-importer har därmed verifierats i en
frikopplad ARM64-testmiljö.** Det är inte ett fungerande STT/TTS-
end-to-end-test eller bevis på mikrofon/högtalarfunktion.

- Godkänd staged-körning med PortAudio/JACK:
  https://github.com/Harrokk/Myai/actions/runs/38232932949
- Skript: `scripts/ventuno_voice_wheel_staging.py` och
  `scripts/ventuno_portaudio_temp_stage.py`.
- Inga `sudo`, `apt install`, `dpkg --install`, modellvikter,
  mikrofonupptagningar, systemd-ändringar eller återstarter användes.

För faktisk röstdrift behöver PortAudio och JACK göras tillgängliga
på ett **stödd och återställningsbart sätt** i produktionsmiljön,
med lämpliga paket, versionskontroller och en rollback-plan.
Detta beslut är **inte** fattat eller automatiskt verkställt.

### Whisper-dependencies: wheel-resolution och senare importtest

`scripts/ventuno_stt_wheel_preflight.py` kan på samma temporära
ARM64-venv göra en begränsad `pip install --dry-run
--ignore-installed --only-binary=:all:` för `faster-whisper`
och dess Python-beroenden. Detta verifierar *paketresolution*,
**inte** att STT-beräkning eller Whisper-modellvikter fungerar.
Det krävs separat minnes-, latens- och modellhanteringstest,
inklusive kontroll av `ctranslate2` och eventuell ARM64-exekvering.

Mikrofontestet `scripts/ventuno_microphone_smoke.py` är fortsatt
**avstängt som standard** och får aldrig köras med inspelning av CI.

## Fullständig ARM64-röstpaketstaging: verifierad utan talmodell (2026-10-12)

Den separata staging-kedjan i
`.github/workflows/ventuno-voice-staging.yml` är nu **godkänd hela vägen**:

1. Kontroll av 13,2 GB tillgängligt RAM och cirka 34 GB ledigt utrymme
   vid start (momentant värde, inte belastningsreserv).
2. Installering av `sounddevice`, `webrtcvad-wheels` och `pyttsx3`
   i en ny tillfällig ARM64-venv. WebRTC VAD och pyttsx3 gick att importera.
3. Temporär hämtning/uppackning av `libportaudio2` och
   `libjack-jackd2-0` från distributionens befintliga apt-källor.
   `sounddevice` kunde då importeras utan systeminstallation.
4. `pip --dry-run --ignore-installed --only-binary=:all:` hittade
   en ARM64-wheel-kedja med **23 paket**, inklusive
   `faster-whisper==1.2.1`, `ctranslate2==4.8.2`,
   `av==19.0.1`, `tokenizers==0.23.3` och
   `onnxruntime==1.31.0`.
5. Faktisk installation av `faster-whisper`-wheels **enbart i
   staging-venv**; `faster_whisper`, `ctranslate2` och `av`
   kunde importeras på VENTUNO ARM64.
6. **Uppmätt peak RSS för separat importprocess: 57,1 MiB**.
   Mätningen använder Linux `resource.ru_maxrss`; processen hade
   en skyddsgräns på 4 GiB virtuellt adressutrymme och 35 CPU-sekunder.
7. Röstflaggorna i aktiv MyAI-profil var fortsatt `false`,
   GenieX/MyAI-tjänsterna aktiva och alla tillfälliga bibliotek
   samt temporära venv-filer borttagna.

Verifierad hårdvarukörning:
https://github.com/Harrokk/Myai/actions/runs/38233884839

**Begränsningar, viktigt:**

- Att CTranslate2 importeras betyder **inte** att rätt Whisper-modell
  kan laddas med vald kvantisering, CPU-arkitektur och minnesbudget.
- 57,1 MiB är **endast bibliotekens importminne**. Modellvikter,
  transkribering, CPU-belastning, latenser och samtidighet med Qwen3-4B
  är fortfarande obevisade.
- Inget `WhisperModel(...)`, ingen nedladdning av talmodellvikter,
  ingen mikrofoninspelning och ingen TTS-ljuduppspelning har gjorts.
- PortAudio/JACK-paketen installerades **inte** i det verkliga OS:et.
  Ett framtida permanent installerat röstsystem kräver separat
  driftsättning med beroendehantering och rollback-plan.

**Nästa steg:** en kontrollerad modellbudget och prestandamätning för
liten svensk STT-modell i staging, separat från Qwen3-processen
och utan parallell laddning, följt av *samtyckesstyrd* mikrofoninspelning.
Inget automatiskt produktionspåslag är tillåtet.

## Verifierad Whisper Tiny-inferens på svenska (2026-10-12)

**Milstolpe:** En riktig `faster-whisper`-modell har nu laddats och
använts för taligenkänning på Arduino VENTUNO Q:s **ARM64-CPU** medan
den befintliga MyAI/GenieX-installationen förblev aktiv, utan
systempaketinstallation eller ändringar i dess röstkonfiguration.

Modelldetaljer:

- Flerspråkig, svenskkompatibel modell:
  `Systran/faster-whisper-tiny` (MIT).
- Låst modellrevision:
  `d90ca5fe260221311c53c58e660288d3deb8d356`.
- Verifierad `model.bin`: 75 538 270 byte, SHA-256
  `dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1`.
- Totalt modellunderlag: 78 203 619 byte.
- `device="cpu"`, `compute_type="int8"`, två CPU-trådar,
  en worker, `language="sv"`, beam size 1.
- Provkörningens ramgräns: minst 8 GiB `MemAvailable`,
  minst 3 GiB fritt diskutrymme; högst 5 GiB virtuellt
  adressutrymme och 115 CPU-sekunder i inferensprocessen.

**Verifierade mätvärden från svensk talprovskörning:**

| Mätpunkt | Resultat |
| --- | --- |
| Modelladdning | **0,558 s** |
| Inferens av 2 s syntetisk tystnad | **1,021 s**, 0 segment |
| Inferens av autentiskt inspelat svenskt ord (1,88 s) | **0,859 s** |
| Svenska referensordet `svenska` identifierat | **Ja** (1 segment) |
| Peak RSS för testprocessen med modellen och ljudet | **239,2 MiB** |
| NPU/HTP använd | **Nej**, CPU-körning |
| Aktiv MyAI/GenieX omstartad eller ändrad | **Nej** |

Testkälla: det offentliga uttalsprovet
[`Sv-svenska.ogg`](https://commons.wikimedia.org/wiki/File:Sv-svenska.ogg),
**Peter Isotalo**, Wikimedia Commons, licenser **CC BY-SA 3.0/GFDL**.
Upphovspersonen anges här och inget ljud materialiseras i projektets
Git-repository; 22 879 byte hämtas endast till en temporär
GitHub-runnerkatalog och verifieras med SHA-1
`817c8f149e5f3b53c0e8200de5a38bfa42756b5a` innan användning.
Ingen användarmikrofon öppnades och inga privata ljuddata hanterades.

Godkänd faktisk VENTUNO-körning:
https://github.com/Harrokk/Myai/actions/runs/38236765378

### PyAV-versionskonflikt upptäckt och löst

Initialt lyckades modelladdning och inläsning av syntetisk tystnad,
men Ogg-inspelningen gav `TypeError`. Problemet var inte
ARM64-modellkompatibiliteten utan kombinationen
`faster-whisper==1.2.1` / `av==19.0.1`:
den äldre Whisper-versionen anropar `av.open` med parametern
`metadata_errors`, som PyAV 19 tagit bort.

Uppströms är detta dokumenterat i
[SYSTRAN/faster-whisper issue #1589](https://github.com/SYSTRAN/faster-whisper/issues/1589).

Vi har därför infört begränsningen **`av>=17,<19`** i
`scripts/ventuno_voice_wheel_staging.py`. På VENTUNO valdes
**`av==18.1.0`**, dess import verifierades och inspelningen
avkodades och transkriberades framgångsrikt.
Versionsbegränsningen ska ses över när en kompatibel
`faster-whisper`-release har testats.

### Vad talprovet INTE verifierar

Ett kort enordsprov är **inte** bevis på konversationsnoggrannhet,
ordfelsprocent (WER), robust bullertålighet, handsfree, mikrofoninput,
högtalare, VAD-baserad upptagning eller samtidighet under hög
Qwen3-4B-inferens. Det ger inte heller något mått på NPU-prestanda.

Lämplig fortsättning: licensierat **längre svenskt talprov** med
ordfelsmätning och flera ljudförhållanden, därefter separat
samtyckesstyrt mikrofon-/högtalartest. Först efter test av
RAM-reserv, latens, lokal ljudrouting och rollback ska röstfunktionen
aktiveras i produktionsprofilen.
