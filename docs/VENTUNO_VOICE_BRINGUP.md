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
