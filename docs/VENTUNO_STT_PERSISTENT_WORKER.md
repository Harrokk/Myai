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


## Verifierad processgruppsstädning – även efter avslutad huvudprocess

Både one-shot- och persistent-läget använder nu `core/voice_stt_process_group.py`.
Tidigare gjordes `SIGKILL` mot processgruppen bara om huvudbarnet fortfarande
var aktivt. Ett hjälpprogram som hade kvar samma processgrupp men överlevde
sin huvudprocess kunde därför fortsätta köras efter att huvudbarnet var
färdigt. Nu undersöks tillhörande Linux-processer i `/proc/*/stat` efter
deras **processgrupps-ID** och signalen skickas även om ledaren redan
har avslutats. Städningen verifierar att inga **levande** medlemmar
återstår och att huvudbarnet är reap:at. Om kontrollen är otillgänglig,
processgruppen inte går att döda eller resurserna inte kan bekräftas
frigjorda rapporteras fel och den cachade STT-processen förblir spärrad.

Testerna är syntetiska: en verklig Python-hjälpprocess sover i 60 sekunder,
medan dess huvudprocess avslutas; nedstängning av processgruppen kontrolleras
på hosted x86 utan mikrofon, talmodell, sudo eller driftsättning på Ventuno.

**Begränsning:** Linux-zombies räknas inte som levande CPU-/RAM-arbete men
kan behöva reap:as av sin nya förälder. Processer som avsiktligt lämnar
sin ursprungliga processgrupp med `setsid()` eller `setpgid()` omfattas
inte av denna mekanism. Inte heller garanteras avslut av processer som
fastnat i kernel D-state. Om MyAI senare måste isolera godtyckliga
barnbarn eller strikt begränsa totala minnet krävs en särskilt granskad
cgroup-v2-lösning och ett separat, säkert distributionstest. Grön CI får
inte förväxlas med den garantin.


## Svarsbundenhet för cachad STT (begärande-ID)

Varje isolerad PCM-förfrågan får ett unikt 16-byte slumpmässigt ID
(128 bitar från `secrets.token_bytes`). Föräldern skickar fyra bytes
PCM-längd, följt av ID och exakt angivet antal PCM-bytes. Arbetaren ekar
ID i svaret (fyra bytes svarsramlängd, 16 bytes ID och högst 8192 bytes
strikt validerad JSON). Föräldern jämför ID med `hmac.compare_digest`
**innan** transkriptet tolkas.

Om ett tidigare eller felaktigt ID anländer, avvisas transkriptet och
den ägda processen avslutas och reap:as innan en ny kan startas.
Syntetiska Linux-tester provar fel ID, en fördröjd svarsruta med
föregående fras-ID, dubbla svar och säker återstart. Funktionen är fortsatt
avstängd som standard och inte driftsatt på VENTUNO.

**Begränsning:** ID:t hindrar inte en illvillig arbetare som själv läser
ett nytt ID från att fabricera ett transkript med det ID:t. Detta är
begärandebindning, inte kryptografisk autentisering av arbetaren eller
ett bevis på STT-kvalitet.


## Stop vid slutlig cleanup och förkortad header

En särskild racekontroll täcker nu sista yttrandets processstädning:
om `Stop` begärs under avslut/reap efter det första avbrottstestet
ska `transcribe()` **inte** lämna tillbaka det färdiga transkriptet.
Avbrott kontrolleras igen **efter** den potentiellt långsamma städningen.
Regression injicerar avbrott exakt i cleanup, kontrollerar avslutat barn
och kräver explicit `resume()` innan nästa syntetiska yttrande.

Tidigare kunde STT-barnet tolka ett avhugget 1–3-byte ramhuvud följt
av EOF som en vanlig, felfri sessionstängning. Nu är **endast EOF innan
någon headerbyte har lästs** normal stängning; en delvis mottagen header
returnerar felstatus utan transkript. Även svar från en äldre worker
utan 16-byte begärande-ID avvisas av föräldern och processen städas.

**Kvarvarande gräns:** Avbrottskontroller kan inte göra hela kedjan
från färdig STT till tal-/verktygsåtgärd atomär. Den överordnade
röstsessionens egna interrupt-/stoppspärrar krävs fortsatt. Tester
använder isolerad källkod och syntetiska bytes; varken mic, riktig
modell, NPU eller driftkonfiguration aktiveras.


## Röst-Stop vid verktygsgränsen (kodgranskning efter PR #224)

En explicit `VoiceSession.stop()` återkallar nu den pågående
röstförfrågans tillstånd **innan** tidskrävande STT/TTS-städning.
`VoicePipeline` använder en unik `threading.Event` per session.
`start()` skapar en ny signal i stället för att nollställa den gamla:
en gammal transkription får därför inte verktygsbehörighet efter
Stop följt av en snabb ny Start.

Verifieraren för verklig MyAICore-verktygskörning bär
`voice_stop_requested`, som läses av
`allow_voice_dispatch()` **före** dess read-only-undantag.
Testerna säkerställer att ett Stop som kommer under planering
avvisar även ett annars tillåtet CPU-läsverktyg samt att
vanliga röstförfrågningar fortfarande fungerar. Ljud-barge-in
(`interrupt()` för TTS) förblir separat från explicit Stop.

**Begränsningar:** Detta kan stoppa **nya** verktygsanrop;
ett verktyg som redan körs kan ha ändrat något och kan inte
alltid avbrytas eller rullas tillbaka. En äldre assistent
som endast implementerar `respond()`, eller förändringar i
minneslagring innan signalen observeras, kräver separat
granskning. Inga tjänster eller modellprov på VENTUNO är aktiverade.


## Stop före långtidsminne och äldre röstgränssnitt

`MyAICore` läser nu samma förfrågningsbundna
`voice_stop_requested`-signal under röstläge. Minnesbedömning,
revisionsförsök, faktisk SQLite-livscykel och köning för
minnesgranskning granskas vid separata avbrottsgränser.
Vid avbrott **före** lagring får en uttrycklig minnesinstruktion
den fasta återkopplingen `not_saved`, utan rått tal eller sökvägar.
Avbrutna röstförfrågningar förs inte in i normalt samtalshistorik.
Även strömmade slutmeddelanden spärras efter Stop och AI-kärnan
avstår från nytt LLM-anrop när avbrottet redan observerats.

Ett äldre assistentobjekt med ett icke-tomt verktygsregister
men **utan** `respond_voice`/`respond_voice_stream` nekas nu
röstverktyg helt, även för läsverktyg; äldre enkla chattobjekt
utan känt verktygsregister kan fortfarande svara. Den sista
typen är inte en generellt verifierad sandlåda.

**Icke-atomisk gräns:** En SQLite-skrivning som hunnit starta
före Stop kan inte avbrytas eller rullas tillbaka automatiskt.
Likaså kan verktyg som startat redan ha orsakat sidoeffekter.
Testerna använder endast syntetisk transkription och lokal,
temporär SQLite, utan verklig mikrofon, modell eller driftsättning.
