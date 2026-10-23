# MyAI – kontroll av verklig syntetiserad startuppmaning före nästa fysiska rösttest

**Datum:** 23 oktober 2026. **Bas:** DRAFT PR #356, exakt HEAD `e7457588f9c455d8d60fff946df85725cf707ab4`. Endast GitHub-hostad ARM64 och källkodstester. **Ingen VENTUNO-åtgärd i denna PR.**

## Pass 1 – upptäckt överlapp mellan uppmaningslängd och säkerhetsspärr

Den förbättrade föreslagna startuppmaningen i PR #356 var: `Vänta en sekund. Säg sedan: Vad heter du.`. Den fysiska rösttestkodens `quiet_wav_from_tts` accepterar **högst 3,5 s** syntetiskt WAV och maximalt **4 % digital toppnivå**, och vägrar spela upp längre ljud. I #356 kontrollerade det fejkade enhetstestet uppmaningens **text**, men ersatte hela TTS-renderingen med ett kort, syntetiskt WAV-klipp. Det verifierade därför **inte** att den nya längre uppmaningen överensstämde med den verkliga hårda WAV-gränsen.

Som preliminär indikator gav lokalt installerad svensk eSpeak-version omkring **3,45 sekunder** för den långa texten, vilket lämnar för liten marginal för skillnader i version/uttalstempo. Detta är **inte en VENTUNO-mätning** och får inte räknas som en bestämd längd för dess eSpeak NG.

## Pass 2 – source-only rättelse och faktisk renderingsverifiering

`scripts/ventuno_usb_dialogue_hardware.py` anger nu en enda centraliserad konstant:
`SPOKEN_START_CUE = "Vänta en sekund. Säg: Vad heter du."`.

Den kortare uppmaningen ger fortfarande ett uttryckligt önskemål om en kort väntan efter högtalaruppspelning, men undviker extramomentet `sedan`. En lokalt tillgänglig annan eSpeak-version gav preliminärt cirka **3,06 sekunder**, vilket fortfarande måste verifieras med projektets verkliga staging av eSpeak NG.

`scripts/ventuno_smoke_cue_render_preflight.py` hämtar exakt samma `SPOKEN_START_CUE` som den framtida fysiska drivrutinen. Den kör **enbart själva talsyntesen** med den redan etablerade tillfälligt extraherade ARM64-eSpeak NG och prövar resulterande minnes-WAV genom **samma** `quiet_wav_from_tts` som normal uppspelning. Resultatet är bara `status`, högsta digitala toppgräns, jämförd varaktighet och fasta boolska säkerhetsflaggor – **inga ljudbytes, ingen verklig taldata och inget transkript**. Den öppnar inte `/dev/snd`, mikrofon, högtalare, NPU eller MyAI:s modell, och kör ingen produktionstjänst.

Testerna i `tests/test_ventuno_smoke_cue_render_preflight.py` använder bara konstgjorda WAV-samples och kontrollerar korrekt text, uppskattad uppspelningstid, in-memory 4 %-gräns, blockering av 3,8 sekunders WAV, trasiga ljud, timeoutliknande avbrott, säkra tillfälliga kataloger, avvisat kommandoeko och **inget test utan uttrycklig syntetisk testflagga**.

Det nya arbetsflödet `.github/workflows/hosted-swedish-cue-render-preflight.yml` använder **endast GitHub-hostad `ubuntu-24.04-arm`**, läsbehörighet till GitHub-källan, en exakt SHA och temporär katalog, och `apt download` + `dpkg-deb --extract` i den katalogen. Det installerar inga systempaket och använder inte VENTUNO-runnern. **Paketets version måste redovisas som miljöberoende**: staging använder tillåtna Ubuntu ARM64-arkiv men pinningen sker inte mot exakt deb-SHA, så det är en faktiskt renderad testversion, inte ett formellt byte-identiskt verifierat VENTUNO-paket.

## Godkännandekrav och kvarstående NO-GO

- GitHub-hostad faktisk eSpeak NG-rendering måste klara 3,5 sekunders varaktighet och digital toppnivå under 4 %.
- Fullständig källkodssvit på **samma slutliga SHA** måste ha 0 fel.
- Om en av dessa kontroller misslyckas får ingen ny fysisk ljudtestkörning skapas från PR:en.
- Den verkliga hårdvarans mikrofon-/ALSA-uppstartstid efter avslutad uppmaning är fortfarande **inte mätt**. En muntlig väntan är en försiktig förberedelse, inte bevis för riktig capture readiness.
- **Användarens tidigare engångssamtycke är förbrukat.** För ny tresekundersinspelning och uppspelning av kort svar krävs ett **nytt separat, uttryckligt godkännande** och övervakning vid den fysiska VENTUNO. Ingen live-inspelning, högtalare, tjänstinstallation, ny produktionsnyckel, `main`-merge eller självmodifiering ingår i detta arbete.

**Produktionsstatus: NO-GO.**
