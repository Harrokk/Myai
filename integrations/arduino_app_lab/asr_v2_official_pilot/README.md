# MyAI v2 — Arduino App Lab officiell ASR-pilot

**Endast för ett framtida manuellt test. Importera gärna som källa, men klicka inte på Run förrän vi uttryckligen har verifierat den lokala miljön och godkänt en ny inspelning.**

Det här är en liten fristående App Lab-applikation som använder Arduinos egen `arduino:asr` Brick. Den använder Arduinos standardmikrofon, utan handskrivna ALSA-inställningar eller en extern Python-Whisper-installation. Det är just den förenklingen som skiljer nya vägen från den arkiverade.

## Körsätt vid framtida särskilt godkänt prov

1. Importera mappen som en Arduino App Lab-app. Appens manifest är `app.yaml` och koden `python/main.py`.
2. Säkerställ lokalt att `whisper-small-quantized` är tillgänglig för den officiella ASR-Bricken. Import i GitHub bevisar inte att modellen är installerad på VENTUNO.
3. Kontrollera vilken mikrofon Arduino App Lab väljer och eventuell konkurrens från den aktiva MyAI/GenieX-tjänsten. Kör inte mot okända enheter och stoppa inga tjänster utan ett nytt godkännande.
4. Vid ett särskilt auktoriserat manuellt `Run` anropas `transcribe_sentence_stream(timeout=8)` en gång, med `language="sv"` och `translate=False`. ASR-Bricken sköter sin standardmikrofons livscykel. Appen använder aldrig externa verktyg.
5. Endast en grov resultatkod visas lokalt: `reference-recognized`, `other-nonempty-final`, `no-final`, `invalid-final`, `unexpected-event`, `event-budget-rejected`, `asr-session-failed` eller `asr-cancel-failed`. Inga transkript eller ljud skickas till GitHub.
6. Avsluta appen manuellt efter provet. Inga röstkommandon, ingen TTS, ingen kontinuerlig lyssning, ingen LLM, inga tjänsteändringar.

Ljudresursen är ännu inte fysiskt verifierad för den här App Lab-appens standardmikrofon. Om MyAI eller GenieX måste pausas för ett prov sker det bara separat med återställningsplan och ditt uttryckliga godkännande. Det äldre ljudarbetet finns oförändrat i grenen `archive/legacy-voice-20261105`.

Officiell referens: Arduino `app-bricks-py` commit `94f100ee906770e6f469f9edbc615bad895d695e`, ASR README och `local_asr.py`. Manifest följer Arduino `app-bricks-examples` för `arduino:asr`.
