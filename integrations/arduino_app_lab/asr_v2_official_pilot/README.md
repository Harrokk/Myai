# MyAI v2 — korrigerad officiell Arduino App Lab-ASR (förberedd, inte körd)

App Lab-piloten kraschade 6 november 2026 redan vid konstruktionen av
`AutomaticSpeechRecognition(language="sv", translate=False)` eftersom Arduinos
automatiska `Microphone(0)` inte såg någon inkopplad mikrofon *inuti App
Lab-containern*. Fel: `MicrophoneOpenError: No microphone found at index 0:
only 0 microphone(s) plugged`.

En **äldre**, separat App Lab-app demonstrerade den 3 november att
`ALSAMicrophone(device="plughw:1,0", shared=False, auto_reconnect=False)`
kunde öppna och leverera ljud till Arduino-ASR (kategorin `pcm-level-present`).
Den gav då `no-final-text`, vilket inte bevisar att svensk igenkänning lyckades.

Det nya försöket byter *endast* mikrofonval och dess livscykel:
- Använd officiell `arduino.app_peripherals.microphone.ALSAMicrophone`, med historiskt observerad `plughw:1,0`. Inget eget PCM-/brus-/Whisper-system.
- Ange `mic=mic` till officiella `AutomaticSpeechRecognition(language="sv", translate=False)`. `App.run` startar ASR; applikationen anropar själv `mic.start()` och `mic.stop()` runt **en** `transcribe_sentence_stream(timeout=8)`.
- Rapportera enbart `microphone-opened`, `microphone-open-failed`, `microphone-release-failed`, `asr-session-failed`, `no-final`, `reference-recognized` eller andra fasta resultatkoder. Ingen inspelning eller transkription loggas.
- Stäng mikrofonen även när ASR misslyckas, ingen automatisk återanslutning eller andra försök.

**Innan ett nytt fysiskt försök:** kontrollera på nytt att USB-kortets nuvarande
ALSA-adress är **1,0**. Appens `plughw:1,0` är baserat på 3 november, inte
den senare rapporten med endast antal USB-mikrofoner. Kontrollera att
App Lab-containern kan se ALSA-enheten. Om kortnumret ändrats: **ändra inte
till en gissad enhet**; använd en bekräftad stabil ALSA-kortidentifierare.
Att ASR-modellen enligt användaren finns installerad bevisar inte att den
fungerar under aktuell servicebelastning.

Ingen ny inspelning godkänns genom att ladda ned eller importera koden.
En separat, uttrycklig begäran krävs innan man klickar **Run** igen.
Stoppa inte MyAI eller GenieX utan godkännande. Ingen äldre röstkod har ändrats.

Kända GitHub-spår: `archive/legacy-voice-20261105` (fryst arkiv),
`dev/app-lab-asr-v2-explicit-alsa-mic-20261106` (detta korrigerade utkast).

## Uppföljning efter första fysiska explicit-mikrofon-testet (6 november)

Användarens verkliga App Lab-logg:
```
App: App started
MYAI_APP_LAB_ASR_V2: microphone-opened
App: App is shutting down
MYAI_APP_LAB_ASR_V2: invalid-final
App shutdown completed
```

Den automatiska mikrofonuppstartskraschen är alltså undanröjd. USB-kort 1 enhet 0 (`plughw:1,0`, Razer Kraken V3 X) är separat bekräftat på värden. Loggen visar en `full_text`-händelse som v2 kodens första version avvisade, men avslöjar inte **vilken** typ av ogiltighet det var. Framför allt kan `full_text` vara blankt under en pågående meningsström; Arduinos referensimplementation väntar på **icke-tom** text.

Denna version hoppar därför över tomma `full_text` inom **samma begränsade åttasekunderssession** (inga nya inspelningar eller omförsök) och avger endast mer särskiljande fasta kategorier: `empty-final-only`, `invalid-final-type`, `invalid-final-too-long`, `invalid-final-control` och befintliga giltiga resultat.

Inget nytt test på den fysiska mikrofonen har startats av kodändringen. Nästa `Run` kräver separat samtycke, och enbart App Labs `failed`-status avgör inte om ASR verkligen har kraschade; granska alltid `[main]`-loggen. MyAI/GenieX lämnas aktiva.

## Uppföljning 11 november – endast tomma ASR-sluthändelser

Användaren har rapporterat `empty-final-only` från nästa fysiska inspelning.
Det betyder att *en eller flera* `full_text` var tomma, inte att ASR
producerade en begriplig transkription. Mikrofonen öppnades i föregående
test och ASR-streamen avvecklades; om ljud faktiskt lästes när användaren
talade är fortfarande obekräftat.

**Källbaserad ny hypotes:** I Arduinos officiella SDK skapas en ASR-session
och dess NPU-modell laddas innan lästråden anropar mikrofonens `capture()`.
Därför kan `microphone-opened` komma långt före faktisk inspelning. Vårt
tidigare försök instruerade användaren att tala vid just denna för tidiga
signal.

Ny version använder en **minimal underklass till Arduinos ALSAMicrophone**
som anropar `super().capture()` och skickar en engångskod
`capture-started-speak-now` först när Arduinos egen lästråd fått en
icke-tom PCM-buffer. Inget PCM tolkas, ändras, kopieras eller lagras;
officiella ASR Brick och originalenheten `plughw:1,0` används som förut.
`microphone-opened-wait-for-capture` är **inte** en uppmaning att tala.
Den nya koden ändrar inte gränsen `timeout=8`, skapar ingen extra session
och gör inga omförsök.

Observera att SDK-lästrådens första PCM-chunk **inte är bevis** att samma
ljud redan har nått inferensservern via WebSocket eller att modellen har
identifierat tal. Det är en källmotiverad, bättre startindikator – inte
en garanti att transkriptionen lyckas.

Ingen ny fysisk inspelning är utförd eller godkänd av denna källkod.
En ny `Run` kräver nytt uttryckligt godkännande. Låt båda MyAI/GenieX
fortsätta köra. Kontrollera Arduino App Lab-modell, mikrofon och tjänster
före en framtida live-körning.
