# MyAI: experimentell isolerad STT med modellcache

**Status:** Kodutkast, avstängt som standard. Inte aktiverat eller prestandamätt på VENTUNO Q med en riktig FasterWhisper-modell.

## Varför

PR #212 införde en separat engångsprocess som kunde dödas om taligenkänning låste sig. Den behöver däremot läsa in modellen igen för varje ljudfras. Den här ändringen lägger till ett valfritt läge som behåller modellen inom **en separat barnprocess under flera yttranden**, men fortfarande tillåter en hård timeout per STT-anrop.

## Konfiguration (endast framtida, granskad testprofil)

Följande nycklar ingår i `voice`:

| Nyckel | Standard | Effekt |
|---|---|---|
| `enabled` | `false` | All röst avstängd |
| `stt_process_isolation_enabled` | `false` | Krävs för isolerade STT-processer |
| `stt_persistent_worker_enabled` | `false` | Aktiverar **valfri** processcache |
| `stt_process_timeout_seconds` | `45.0` | Högst 1–300 sekunder per IPC-anrop |
| `stt_persistent_worker_max_utterances` | `4` | Högst 1–8 yttranden per barnprocess |

Bara den inbyggda FasterWhisper-providern och tillåtna modellnamn/PCM-format stöds. Ingen talmodell laddas när modulen importeras eller när funktionen är avstängd.

## Säkerhet och livscykel

- Ett enda process-ID återanvänds för flera konsekutiva yttranden. Föräldern skickar högst **2 MiB** PCM via anonyma pipes och får högst **8192 bytes** JSON tillbaka med strikt schema. Ingen ljud- eller transkriptdata skrivs till projektloggar.
- En monotont uppmätt deadline omfattar **både skrivning och läsning**. Pipes är icke-blockerande för att undvika att ett stort meddelande hänger i `write()`. En process som ger timeout eller ogiltiga data avslutas och reap:as; nästa anrop får en ny process.
- Processen begränsas till 1–8 yttranden, så att långvarig native minnesfragmentering inte får obegränsad livstid. När röstsessionen stängs anropas `close()` på processens ägande STT-providers. `release_for_inference()` kan frigöra modellen inför tyngre LLM-anrop om profilen redan använder STT-handoff.
- `python -I`, fast arbetsfil, explicit minimal miljö, offline HuggingFace och inga ärvda åtkomsttoken. `subprocess` kör utan shell, användardefinierade kommandon eller externa URL:er.
- Detta stoppar **en kontrollerbar barnprocess** men garanterar inte avbrott av Linux-D-state, system-wide OOM eller en maskin som hängt sig. En stängd process kan behöva laddas om nästa gång, och modellcache kan kosta betydande RAM när GenieX används samtidigt.

## Verifiering

CI använder riktiga Linux-barnprocesser med **syntetiska bytes** för att testa återanvändning, timeout, proc-gruppsavslut, återstart, malformed JSON och frigöring vid sessionsstopp. Den fysiska VENTUNO-runningsdelen kontrollerar **enbart källkod och standardavstängt läge**; den startar inte Whisper-modeller, DSP eller mikrofon.

Innan aktivering krävs faktisk CPU-/RAM-/latensmätning med representativ talmodell och full duplex. Dessa fysiska moment finns fortsatt parkerade i [Fysiskt närvarande tester](PHYSICAL_PRESENCE_TESTS.md).

**Ingen automation får slå på detta i produktion bara för att testerna är gröna.**
