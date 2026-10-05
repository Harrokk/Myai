# MyAI – Project Specification

## 1. Syfte

MyAI ska vara en lokal, personlig AI-assistent som i första hand körs lokalt på användarens egen hårdvara men som kan använda internet när det behövs.

Systemet ska vara modulärt, utbyggbart och kunna växa från nuvarande Windows-baserade utvecklingsmiljö till att i framtiden köras på en Arduino VENTUNO Q med Qualcomm Dragonwing IQ-8275 och 16 GB RAM.

Målet är att skapa en AI-assistent som kan förstå naturliga röstkommandon, arbeta med lokal hårdvara och externa enheter, använda verktyg, läsa och ändra filer, skriva kod, testa uppdateringar och ge tydliga svar utan att hitta på information.

---

## 2. Grundprinciper

### 2.1 Lokal drift först
AI:n ska i första hand köras lokalt.

Internet ska användas när det behövs, till exempel för:
- väder
- aktuell information
- webbsökningar
- externa tjänster
- uppgifter som den lokala modellen eller lokala databasen inte kan lösa på ett tillförlitligt sätt

### 2.2 Ingen gissning när fakta saknas
AI:n ska inte hitta på svar.

Om tillräcklig information saknas ska AI:n tydligt säga att den inte vet eller inte kan verifiera svaret.

När det är lämpligt ska den även kunna föreslå:
- vilken information som saknas
- hur informationen kan tas fram
- var användaren själv kan leta
- vilket verktyg eller vilken sensor som skulle behövas

### 2.3 Naturlig interaktion
Användaren ska kunna prata med AI:n med vanliga röstkommandon och normalt språk.

Användaren ska inte behöva känna till interna kommandon, funktionsnamn eller programmeringssyntax för normala uppgifter.

---

## 3. Målplattform

### Nuvarande utvecklingsmiljö
- Windows-PC
- NVIDIA GeForce RTX 3060 12 GB
- Ollama
- Qwen3:8b
- Python
- SQLite-baserat minne
- modulärt verktygssystem

### Framtida målplattform
- Arduino VENTUNO Q
- Qualcomm Dragonwing IQ-8275
- 16 GB LPDDR5 och 64 GB eMMC
- Qualcomm GenieX/QAIRT som primär lokal AI-backend
- Qwen3-4B som planerad normal lokal språkmodell
- separat STM32-baserad realtidsdel för tidskritisk I/O
- möjlighet att ansluta externa sensorer, terminaler och annan hårdvara

Arkitekturen ska byggas så att så mycket kod som möjligt kan återanvändas vid flytten från Windows till VENTUNO Q. Ollama ska fortsatt kunna användas i Windows-utvecklingsmiljön medan AI-kärnan använder ett provider-neutralt gränssnitt mot vald lokal modellmotor.

Raspberry Pi-stödet som redan finns i projektet behålls som alternativ hårdvaruprofil och som återanvändbara Linux-/GPIO-moduler, men Raspberry Pi 5B är inte längre primär målplattform.

---

## 4. Röst och ljud

AI:n ska kunna användas som en röstassistent.

### 4.1 Modulär röstarkitektur

Röstfunktionen ska byggas som en separat modul runt AI-kärnan.

Grundflödet ska vara:

**Mikrofon → röstaktivitetsdetektering → tal-till-text → MyAI-kärna → vald lokal LLM-provider → text-till-tal → hörlurar/högtalare**

Röstmodulen ska kunna bytas eller uppgraderas utan att dialogsystemet, minnet eller verktygssystemet behöver skrivas om.

### 4.2 Valbar röst, accent och talstil

AI:n ska kunna använda olika röster och talstilar när den valda text-till-tal-motorn stöder detta.

Exempel på framtida kommandon:
- "Prata långsammare."
- "Använd en mörkare röst."
- "Prata mer neutralt."
- "Kan du ha skånsk brytning?"
- "Byt tillbaka till standardrösten."

Systemet ska skilja mellan:
- språkmodellens personlighet och ordval
- text-till-tal-motorns röst
- accent eller dialekt
- talhastighet
- tonläge
- pauser och prosodi

Om den installerade röstmotorn inte kan skapa en viss accent eller dialekt ska AI:n säga det tydligt i stället för att låtsas.

Röstinställningar ska kunna sparas som användarpreferenser i långtidsminnet när de återkommer eller uttryckligen väljs som standard.

### 4.3 Avbrott under tal

Användaren ska kunna avbryta AI:n medan den pratar.

När användaren börjar tala eller använder ett avbrottskommando ska systemet kunna:
1. stoppa pågående text-till-tal
2. börja lyssna på användaren
3. behålla relevant samtalskontext
4. hantera den nya instruktionen utan att användaren behöver vänta på att hela svaret läses upp

Detta ska göra röstinteraktionen mer naturlig och minska känslan av att använda en vanlig textbot med uppläsning.


### 4.5 Redundant taligenkänning och konsensus

För viktig eller osäker röstinmatning ska MyAI kunna använda flera oberoende tal-till-text-tolkningar och jämföra resultaten innan kommandot skickas vidare till AI-kärnan.

Målet är att minska risken att ett felaktigt hörfel leder till fel handling.

Ett möjligt högsäkerhetsflöde är:

**Mikrofon → tre STT-tolkningar → semantisk jämförelse → confidence-vägning → konsensus → osäkerhetskontroll → MyAI**

Systemet ska inte kräva exakt identisk text från de olika tolkningarna. I stället ska det kunna avgöra om formuleringarna betyder samma sak.

Exempel:

- "Hur mycket RAM använder datorn?"
- "Hur mycket ram använder min dator?"
- "Hur mycket RAM-minne används?"

ska kunna betraktas som samma avsikt.

Om två tolkningar är tydligt överens och en tredje avviker ska systemet kunna välja majoritetstolkningen.

Om resultaten fortfarande är osäkra eller motsägelsefulla ska MyAI fråga användaren om förtydligande i stället för att gissa.

### 4.6 Adaptiv säkerhetsnivå för tal

Redundant taligenkänning ska kunna användas adaptivt för att undvika onödig belastning och fördröjning.

Normal låg-risk-dialog kan använda en snabb primär STT-tolkning.

Ytterligare tolkningar ska kunna aktiveras när:
- den första transkriptionen har låg confidence
- flera ord är osäkra
- kommandot påverkar filer eller kod
- kommandot ändrar systeminställningar
- kommandot styr fysisk hårdvara
- kommandot kan radera eller skriva över data
- användaren uttryckligen begär hög säkerhet

På kraftfull hårdvara kan tre tolkningar köras parallellt.

På den framtida målplattformen ska systemet kunna använda en resurssnål strategi där extra tolkningar endast körs vid behov.

### 4.7 Säkerhet före gissning

För röstkommandon med potentiellt stora konsekvenser ska MyAI hellre:
1. göra en extra taligenkänning
2. jämföra resultaten
3. kontrollera kommandots innebörd
4. fråga om förtydligande eller bekräftelse när det fortfarande finns rimlig osäkerhet

än att utföra en handling baserad på en osäker transkription.

### 4.4 Lokal och framtidssäker röstbehandling

På den nuvarande Windows-datorn ska systemet kunna använda en kraftfull lokal lösning för taligenkänning och text-till-tal.

Vid framtida flytt till VENTUNO Q ska röstmodulerna kunna använda Qualcomm-accelererade alternativ utan att resten av MyAI behöver ändras.

Röstbehandling ska i första hand kunna fungera lokalt, men externa tjänster ska kunna användas som valbara verktyg om användaren tillåter det och det ger en tydlig fördel.


Önskade funktioner:
- ta emot talade kommandon
- svara med tal
- fungera med Bluetooth-anslutna in-ear-hörlurar
- låta användaren styra funktioner med naturligt språk
- kunna läsa upp listor, statusinformation och resultat

På sikt ska användaren kunna använda AI:n utan att behöva titta på en skärm.

### 4.8 Teknisk status för lokal röstpipeline

På utvecklingsgren finns nu ett komplett, men standardavstängt, lokalt röstlager
runt MyAI-kärnan. Lagret är byggt så att mikrofon, VAD, STT och TTS kan bytas
utan att dialog-, minnes- eller verktygskoden behöver skrivas om.

Den nuvarande provideruppsättningen stöder:
- mikrofonramar via `sounddevice`
- WebRTC VAD
- lokal STT via `faster-whisper`
- lokal TTS via `pyttsx3`
- interruptibel/asynkron TTS
- kontinuerlig handsfree-session i separat daemontråd
- primär STT plus valfria redundanta STT-tolkningar
- syntaktisk och valfri semantisk konsensus
- adaptiv extra STT vid låg confidence och högriskkommandon
- eko-skydd mot att nyligen uppläst TTS återtolkas som nytt användarkommando
- explicit röstbekräftelse före högriskkommandon

Standardläget är `voice.enabled=false` och `voice.tts_enabled=false`.
Röstberoendena ligger separat i `requirements-voice.txt`, så grundinstallationen
behöver inte installera eller initiera ljudbiblioteken.

VAD-state machine, STT-konsensus, semantisk resolver, providergränssnitt,
session, handsfree-loop, TTS-avbrott, eko-skydd och riskbekräftelse testas med
mockade ljudproviders i CI. Verklig mikrofon, ljudkort, Bluetooth-headset,
full-duplex, praktisk latens, röstkvalitet och verkligt barge-in ska verifieras
senare i den samlade hårdvarurundan.

---

## 5. Bluetooth

AI:n ska kunna hantera Bluetooth via naturliga kommandon.

Önskade funktioner:
- aktivera och avaktivera Bluetooth
- söka efter Bluetooth-enheter i närheten
- lista hittade enheter
- läsa upp hittade enheter
- identifiera kända och okända enheter
- ansluta till tillåtna enheter
- upptäcka när nya Bluetooth-enheter dyker upp
- kunna fråga användaren om en ny enhet ska konfigureras

### Avstånd / närhet
AI:n ska kunna uppskatta avstånd eller närhet till Bluetooth-enheter när hårdvaran och Bluetooth-protokollet tillåter det.

Detta kan till exempel baseras på signalstyrka, RSSI eller annan tillgänglig mätdata.

Systemet ska vara tydligt med att en sådan uppskattning inte är samma sak som exakt GPS-avstånd.

### 5.1 Teknisk status för närhetsmätning

På utvecklingsgren finns nu ett separat Bluetooth-närhetslager för BLE-enheter. Det kan normalisera RSSI, klassificera signalstyrkan till försiktiga närhetsnivåer och göra en grov meteruppskattning med en konfigurerbar radiomodell. Beräkningen använder annonserad TX-effekt när den finns och annars ett dokumenterat standardvärde.

BLE-skanning använder Bleak som plattformsoberoende gränssnitt. Logiken kan automatiskt testas i CI, men riktig RSSI-data, Windows Bluetooth-adapter, radiomiljö och praktisk avståndsuppskattning måste verifieras lokalt på den fysiska datorn innan funktionen betraktas som fullt verifierad.

Den samlade hårdvaruverifieringen innehåller därför nu även ett Bluetooth-steg som kräver minst en annonserande BLE-enhet med användbart RSSI-värde.

---

## 6. Automatiska terminalanslutningar

AI:n ska i framtiden kunna ansluta automatiskt till särskilda terminaler eller andra betrodda enheter.

Exempel:
- terminal i bilen
- terminal i hemmet
- andra framtida noder

Systemet ska kunna:
- känna igen en betrodd terminal
- bedöma om den är tillräckligt nära
- ansluta automatiskt enligt definierade regler
- koppla från eller byta terminal när förutsättningarna ändras

Tröskelvärden och anslutningsregler ska kunna konfigureras.

### 6.1 Teknisk status för betrodda terminaler

På utvecklingsgren finns nu ett komplett, standardavstängt terminalhandoff-lager.
Policyn kräver att terminalen uttryckligen finns i konfigurationen, är markerad
som betrodd och har automatisk anslutning aktiverad. Separata RSSI-trösklar
för anslutning och frånkoppling ger hysteres.

Handoff-monitorn kräver dessutom flera efterföljande starka respektive svaga
eller missade skanningar innan ett connect/disconnect-event skapas. Detta
minskar risken för att en terminal växlar tillstånd på grund av enstaka
radiomätningar.

Standardläget är säkert:
- `trusted_terminals.enabled=false`
- `auto_execute=false`
- `connector_provider="none"`
- listan över betrodda terminaler är tom
- connect kräver normalt två bekräftande skanningar
- disconnect kräver normalt tre bekräftande svaga/missade skanningar

När explicit aktiverat finns en BLE GATT-connector via Bleak. Den ansluter
endast till en terminal som är markerad som betrodd, har
`transport="bleak_gatt"` och normalt har ett förväntat `service_uuid`.
Efter anslutning verifieras att den förväntade GATT-servicen faktiskt finns;
annars kopplas klienten från igen.

Policy, hysteres, handoff-state machine, fail-closed-beteende, providerfactory,
GATT-servicekontroll och connect/disconnect-livscykel testas i CI med mockad
scanner och mockad BLE-klient. Två separata lokala verifieringsskript finns
för framtida riktig RSSI/handoff respektive explicit GATT connect/disconnect.

Riktig Windows Bluetooth-adapter, annonserande BLE-terminal, fysisk RSSI,
praktiska närhetströsklar, GATT-service och stabil connect/disconnect är nu
hårdvaruverifiering och ska inte betraktas som godkända förrän de lokala
testen har körts.

---

## 7. Raspberry Pi – systemåtkomst

AI:n ska kunna läsa och förstå så mycket som möjligt av Raspberry Pi-systemets status.

Exempel:
- CPU-belastning
- RAM-användning
- lagringsutrymme
- temperatur
- strömförbrukning
- spänning
- eventuell throttling
- anslutna USB-enheter
- nätverk
- Bluetooth
- tillgängliga portar och gränssnitt
- systemloggar
- processer och tjänster

AI:n ska kunna svara på frågor som:
- Hur varm är datorn?
- Hur mycket RAM används?
- Hur mycket ström drar systemet?
- Finns risk för överhettning?
- Vilka USB-enheter är inkopplade?
- Vilka portar finns tillgängliga?

### 7.1 Teknisk status för Raspberry Pi-systemdata

På utvecklingsgren finns nu ett separat verktyg `pi_system_status` som är byggt för att kunna köras på Raspberry Pi utan att Windows-koden behöver skrivas om.

Verktyget kan samla:
- Raspberry Pi-modell
- CPU-belastning och kärnor
- RAM-användning
- lagringsutrymme
- CPU-temperatur
- kärnspänning när `vcgencmd` finns
- aktuell och historisk throttling/underspänning via `get_throttled`

På en dator som inte är en Raspberry Pi ska verktyget avsluta säkert och tydligt säga att Raspberry Pi inte upptäcktes.

Tolkningen av Raspberry Pi:s throttling-bitar och övrig logik testas i CI. Faktisk avläsning av temperatur, spänning och throttling ska verifieras fysiskt på Raspberry Pi i en senare samlad Pi-hårdvarurunda.

### 7.2 Read-only systemdiagnostik

På utvecklingsgren finns nu separata read-only-verktyg för:
- nätverksgränssnitt, länkstatus och IP-adresser via `pi_network_status`
- processöversikt med CPU/RAM via `pi_process_status`
- körande systemd-tjänster via `pi_services_status`
- senaste systemloggar på warning-nivå eller högre via `pi_system_logs`

Verktygen gör inga ändringar i nätverk, processer, tjänster eller loggar. De ska kunna användas separat eller kombineras genom multi-tool-stödet när en fråga kräver flera diagnostikkällor samtidigt.

På icke-Linux-plattform ska verktygen avsluta säkert och förklara att Raspberry Pi/Linux krävs. Parsning, formattering och felhantering testas i CI. Verklig nätverks-, process-, systemd- och journald-data ska verifieras senare i den samlade Raspberry Pi-hårdvarurundan.

### 7.3 Read-only ström- och effekttelemetri

På utvecklingsgren finns nu verktyget `pi_power_status`. Det läser standardiserade Linux `hwmon`-mätvärden för effekt, spänning och ström när Raspberry Pi, PMIC och installerade drivrutiner faktiskt exponerar dem.

MyAI ska inte räkna fram eller gissa en strömförbrukning när ett verkligt mätvärde saknas. Om `hwmon` inte exponerar effekt/ström/spänning ska svaret därför uttryckligen säga att telemetri saknas.

Enhetsomvandling och felhantering testas i CI med simulerade `hwmon`-sensorer. Vilka mätkanaler som faktiskt finns på den framtida Raspberry Pi 5B-installationen ska verifieras i den samlade Pi-hårdvarurundan.

---

## 8. Raspberry Pi – GPIO och hårdvara

AI:n ska känna till Raspberry Pi:ns ingångar och utgångar och kunna hjälpa användaren med fysisk inkoppling.

Den ska kunna förklara:
- vilken pinne som ska användas
- vilka GPIO-pinnar som finns
- 3,3 V
- 5 V
- jord
- I2C
- SPI
- UART
- USB
- andra relevanta gränssnitt

AI:n ska kunna svara på frågor i stil med:
- Var ska jag koppla in den här sensorn?
- Vilken GPIO kan jag använda?
- Behöver den här komponenten 3,3 eller 5 volt?
- Hur kopplar jag detta utan att skada Raspberry Pi?

Vid hårdvaruinkoppling ska AI:n prioritera säkerhet och inte gissa om elektriska värden.

### 8.1 Teknisk status för GPIO-referens och säkerhetskontroll

På utvecklingsgren finns nu ett separat Raspberry Pi GPIO-lager med en normaliserad referens för standard-headern med 40 pinnar.

Lagret innehåller:
- fysisk pin till BCM-GPIO-mappning
- fasta 3,3 V-, 5 V- och GND-pinnar
- I2C-, SPI0- och UART-standardpinnar
- markering av GPIO0/GPIO1 som reserverade för HAT-ID/avancerad användning
- konservativ förkontroll av föreslagna inkopplingar

Säkerhetskontrollen kan returnera `allow`, `warn` eller `block`. Den ska bland annat blockera 5 V-signal direkt till en 3,3 V GPIO, direktdrift av motor/solenoid och LED utan verifierad strömbegränsning.

Reglerna baseras på Raspberry Pi:s officiella GPIO-dokumentation. MyAI ska fortfarande kräva komponentens datablad när märkspänning, strömbehov eller elektrisk kompatibilitet inte är känd.

GPIO-logiken och pinmappningen testas i CI. Faktiska fysiska inkopplingar och GPIO-åtkomst ska verifieras senare på Raspberry Pi-hårdvaran innan styrande funktioner tillåts.

### 8.2 Read-only inventering av Pi-gränssnitt

På utvecklingsgren finns nu ett separat read-only-verktyg `pi_interfaces_status` som inventerar vanliga Linux-enhetsnoder för:
- GPIO-chip
- I2C
- SPI
- UART/seriella portar

Verktyget gör inga ändringar i systemet och försöker inte aktivera gränssnitt. Om det körs på Windows eller annan icke-Linux-plattform avslutar det säkert och förklarar att fysisk Pi-inventering kräver Linux/Raspberry Pi.

När MyAI senare körs på Raspberry Pi kan denna inventering användas för att skilja mellan vad Pi-modellen teoretiskt stödjer och vilka gränssnitt som faktiskt är exponerade i det körande operativsystemet.

Den verkliga enhetsinventeringen ska verifieras i den samlade Raspberry Pi-hårdvarurundan.

### 8.3 Read-only inventering av kernel-registrerade bussenheter

På utvecklingsgren finns nu verktyget `pi_bus_devices_status`. Det läser Linux sysfs och listar I²C- och SPI-enheter som kärnan redan känner till.

Verktyget gör ingen aktiv buss-skanning. Det använder inte `i2cdetect`, skickar inga sonderingskommandon och skriver inte till någon enhet. Därmed minskas risken att en känslig sensor påverkas bara för att MyAI inventerar systemet.

För I²C kan verktyget visa buss, adress, namn och drivrutin när informationen finns. För SPI kan det visa controller, chip-select, modalias/namn och drivrutin.

Om inga kernel-registrerade enheter finns ska MyAI säga det tydligt och inte tolka det som bevis för att bussen är elektriskt tom. Fysisk verifiering av verkliga sensorer och bussar sparas till den samlade Raspberry Pi-hårdvarurundan.

---

## 9. Automatisk upptäckt av hårdvara

AI:n ska kunna upptäcka när ny hårdvara ansluts.

### 9.1 Teknisk status

Pågående implementation innehåller:
- generell hårdvaruinventering via `hardware_inventory`
- normaliserade snapshots av närvarande enheter
- lokal snapshotfil under `runtime/` som inte versionshanteras
- jämförelse mellan föregående och aktuell snapshot
- identifiering av nya, borttagna och statusändrade enheter via `hardware_changes`

Första körningen skapar en baslinje. Senare körningar kan rapportera förändringar. Automatisk kontinuerlig övervakning är nu implementerad på utvecklingsgren via en konfigurerbar bakgrundsmonitor. Den kan startas och stoppas från terminalen med `/watch on` och `/watch off`, och rapporterar nya, borttagna eller statusändrade enheter utan att en användarfråga krävs. Funktionen ska lokalt hårdvaruverifieras innan merge.

Ovanpå detta finns nu ett persistent enhetsregister under `runtime/device_registry.json`. Nya enheter som upptäcks av övervakningen registreras initialt som okända. Terminalkommandona `/devices` och `/devices unknown` visar registret, och `/device known ID` kan markera en registrerad enhet som känd. Bakgrundsövervakningen informerar om nya okända enheter men gör inga interaktiva eller riskfyllda konfigurationsändringar från bakgrundstråden.

Ett samlat lokalt verifieringsskript finns i `scripts/hardware_validation.py`. Det återanvänder smoke-testet, kontrollerar hårdvaruinventeringen och leder användaren genom borttagning och återanslutning av en fysisk test-enhet. Resultatet sparas lokalt under `runtime/` och versionshanteras inte.


Exempel:
- USB-enheter
- Bluetooth-enheter
- framtida sensorer
- externa terminaler

När en okänd enhet upptäcks ska AI:n kunna:
1. identifiera vad som går att läsa ut om enheten
2. informera användaren
3. fråga om enheten ska konfigureras
4. spara relevant konfiguration efter godkännande

### 9.2 Godkännandeflöde för nya enheter

På utvecklingsgren finns nu ett explicit godkännandeflöde ovanpå enhetsregistret. Nya enheter registreras med status `pending` och får inte automatiskt betraktas som kända eller konfigurerade.

När en ny okänd enhet upptäcks ska terminalen visa den identifierbara informationen och ett tydligt val:
- `/device approve ID` för att godkänna och spara enheten
- `/device reject ID` för att avvisa konfigurationen

Ett godkännande sparar beslutet persistent i det lokala enhetsregistret. Ett avslag sparas också så att systemet kan skilja mellan en ny väntande enhet och en enhet som användaren aktivt har avvisat.

Bakgrundsövervakningen får informera om en ny enhet men ska inte själv godkänna eller konfigurera den. Beslutet ska komma från användaren eller från en framtida uttryckligt definierad och säker policy.

---

## 10. Filer och dokument

AI:n ska kunna arbeta med vanliga filer och dokument.

Särskilt viktigt:
- skapa Excel-filer
- läsa Excel-filer
- ändra befintliga Excel-filer
- lägga till eller ändra data
- skapa tabeller
- utföra beräkningar
- spara resultat på ett kontrollerat sätt

På sikt kan systemet även utökas till fler dokumentformat.

### 10.1 Teknisk status för sandboxade filer och Excel

På utvecklingsgren finns nu en separat lokal dokumentyta under `runtime/workspace`.
Allmän filåtkomst normaliserar användarens sökvägar och blockerar absoluta
sökvägar samt path traversal utanför denna yta.

Read-only-funktioner kan lista och läsa tillåtna filer. Allmän skrivning är
avstängd som standard och kan endast aktiveras genom konfiguration. Den
allmänna skrivaren tillåter endast `.txt`, `.md`, `.csv` och `.json`;
körbar Python-kod och andra filtyper kan inte skapas genom detta verktyg.

Excel-lagret arbetar separat med `.xlsx` och kan:
- skapa arbetsböcker med kolumner och rader
- läsa arbetsböcker och formler
- lägga till rader
- ändra enskilda celler i A1-format
- välja och lista namngivna blad
- skapa nya blad

Excel-skrivning är också avstängd som standard. Skrivningar använder temporär
fil och atomisk ersättning för att minska risken för halvskrivna arbetsböcker.
`openpyxl` ligger som ett valfritt beroende och behöver bara installeras när
Excel-funktionerna faktiskt ska användas.

Sökvägssäkerhet, read/write-spärrar, naturlig språkparsning, cellreferenser,
bladval och filoperationer testas i CI. Dessa funktioner kräver ingen fysisk
hårdvara.


---

## 11. Programmering och självuppdatering

AI:n ska kunna hjälpa till att utveckla sin egen kodbas.

### 11.1 Dynamisk kompetensutbyggnad

AI:n ska vara dynamisk och kunna identifiera när den saknar en förmåga som krävs för att lösa en uppgift.

Om användaren ber om något som assistenten inte kan göra med sina befintliga verktyg eller moduler ska den, när det är tekniskt rimligt och säkert, kunna:

1. identifiera vilken funktion eller vilket verktyg som saknas
2. föreslå en teknisk lösning
3. skapa ny kod eller en ny modul i en separat arbetsmiljö
4. installera eller simulera nödvändiga beroenden i en isolerad sandbox när det behövs
5. testa den nya funktionen utan att påverka den aktiva assistenten
6. köra relevanta automatiska tester
7. kontrollera fel, säkerhetsproblem och oväntade bieffekter
8. rapportera testresultatet tydligt till användaren
9. visa vad som kommer att ändras innan implementering
10. endast implementera ändringen i den riktiga assistenten efter godkänt test och enligt gällande säkerhetsregler

Exempel:

> Användaren ber AI:n att läsa data från en ny typ av sensor som det ännu inte finns något verktyg för.

AI:n ska då kunna konstatera att funktionen saknas, skapa ett nytt sensorverktyg i sandbox, testa kommunikationen och återkomma med resultatet innan någon permanent ändring görs.

### 11.2 Sandbox som obligatoriskt mellanled

Ny eller ändrad självgenererad kod ska som huvudregel aldrig köras direkt i den aktiva assistenten.

Arbetsflödet ska vara:

**Aktiv version → arbetskopia → kodändring → sandbox-test → resultatrapport → godkännande → implementering → verifiering**

Sandbox-miljön ska så långt som möjligt:
- vara separerad från den aktiva kodbasen
- använda kopior av nödvändiga filer
- begränsa åtkomst till känsliga filer och systemfunktioner
- kunna återställas efter test
- logga vad som kördes och vilket resultat det gav

Om en funktion inte kan testas säkert eller tillräckligt realistiskt i sandbox ska AI:n tydligt säga det i stället för att låtsas att testet är tillräckligt.

### 11.3 Implementering efter test

Efter ett lyckat sandbox-test ska AI:n återkomma med:
- vad den byggde
- vilka filer som ändrades eller skapades
- vilka tester som kördes
- vilka tester som lyckades eller misslyckades
- kända begränsningar
- eventuella säkerhetsrisker
- förslag på nästa steg

Den aktiva assistenten ska inte uppdateras bara för att koden går att köra. Testresultatet ska först bedömas och implementationen ska ske kontrollerat med möjlighet till rollback.


Önskat arbetsflöde:

1. AI:n analyserar den aktuella koden.
2. AI:n skapar en kopia eller separat arbetsversion.
3. Den gör önskade kodändringar i arbetsversionen.
4. Den kör automatiska tester.
5. Den analyserar testresultaten.
6. Den rapporterar vad som fungerade och vad som inte fungerade.
7. Om testerna lyckas kan den föreslå att ändringen implementeras.
8. Implementering i den aktiva versionen ska ske kontrollerat.
9. Det ska finnas möjlighet att återställa en tidigare fungerande version.

AI:n ska inte skriva över sin fungerande kod utan skyddsmekanismer.

### Viktiga skydd
- versionshantering med Git
- separat testgren eller arbetskopia
- automatiska tester
- backup
- rollback
- loggning av förändringar
- användargodkännande för riskfyllda eller större ändringar

På sikt kan säkra, vältestade och lågriskändringar eventuellt automatiseras mer.

---

## 12. Verktygssystem

AI:n ska använda modulära verktyg.

Ett verktyg ska vara en separat funktion eller modul som AI:n kan anropa vid behov.

Exempel på verktyg:
- GPU-status
- CPU-status
- RAM-status
- temperatur
- lagring
- Bluetooth
- USB
- GPS / position
- internet
- väder
- Excel
- filhantering
- systemstatus
- framtida sensorer

AI:n ska kunna välja flera verktyg för samma fråga.

Exempel:

> Hur mycket CPU och RAM använder datorn?

ska kunna köra både CPU- och RAM-verktyget och kombinera resultaten i ett svar.

---

## 13. Internet

AI:n ska fungera lokalt men kunna använda internet när det behövs.

Exempel:
- väder
- nyheter
- webbsökning
- dokumentation
- kartinformation
- uppdaterad teknisk information

Exempel på fråga:

> Vad blir det för väder idag i Åkersberga?

AI:n ska då kunna identifiera att aktuell extern information krävs, hämta den och svara.

Internetåtkomst ska vara ett verktyg, inte ett krav för att grundfunktionerna ska fungera.

### 13.1 Prisjämförelse och köp från Sverige

När användaren ber MyAI att hitta en produkt eller det bästa priset ska assistenten kunna söka på internet och jämföra verkligt användbara köpalternativ, inte enbart sortera på lägsta listpris.

Exempel:

> Hitta bästa pris på en ESP32.

MyAI ska då så långt som möjligt väga in:
- produktpris
- frakt till Sverige
- moms och tydligt angivna avgifter
- lagerstatus
- om säljaren faktiskt levererar till Sverige
- beräknad eller angiven leveranstid när den finns
- butikens och säljarens trovärdighet
- rimliga betalnings- och köparskydd

Standardresultatet ska kunna presentera de tre billigaste alternativen som samtidigt bedöms som tillräckligt tillförlitliga och praktiskt möjliga att beställa från Sverige. Varje alternativ bör, när informationen finns, visa totalpris, butik, leveransinformation och direktlänk.

MyAI ska kunna sortera bort eller tydligt varna för alternativ med starka varningssignaler, till exempel otydlig avsändare, tveksam företagsinformation, osäkra betalningsmetoder, misstänkt kopierat innehåll eller andra tecken på att sidan kan vara opålitlig.

MyAI ska inte garantera att en butik är säker när underlaget är otillräckligt. Vid osäkerhet ska den säga det tydligt och beskriva vad som inte har kunnat verifieras.

### 13.2 Källgranskning och konfidensbedömning

Vid informationssökning ska MyAI inte enbart hämta ett svar utan även granska underlaget.

Systemet ska skilja mellan två separata bedömningar:
1. **Källans tillförlitlighet** – hur trovärdig och relevant själva källan verkar vara.
2. **Informationens konfidens** – hur starkt det aktuella påståendet stöds av tillgängliga uppgifter.

Bedömningen ska bland annat kunna väga in:
- primärkälla kontra återberättande
- tydlig avsändare, författare och ansvarig organisation
- källans aktualitet i förhållande till frågan
- metod, dokumentation och transparens
- oberoende bekräftelse från flera källor
- om flera källor i praktiken bygger på samma ursprungskälla
- samstämmighet och eventuella motsägelser
- om källan har ett tydligt kommersiellt eller annat intresse som kan påverka innehållet

MyAI ska kunna presentera bedömningarna som tydliga konfidensnivåer eller procentsiffror, exempelvis:
- Källans tillförlitlighet: 90 %
- Informationens konfidens: 75 %

En sådan procentsiffra ska beskrivas som en intern konfidensbedömning och inte som en matematisk garanti för att informationen är sann, om systemet inte senare använder en särskilt kalibrerad sannolikhetsmodell.

Om trovärdiga källor motsäger varandra ska MyAI visa detta, sänka konfidensen och förklara vilka uppgifter som stödjer respektive motsäger påståendet. Vid låg säkerhet ska assistenten säga att informationen är osäker i stället för att gissa.


### 13.3 Fem kandidater → validering → topp tre

När en internetuppgift innebär att MyAI ska jämföra, välja mellan eller rekommendera alternativ ska standardflödet vara:

1. samla in upp till fem rimliga och relevanta kandidater eller källor
2. kontrollera att kandidaterna faktiskt är användbara för frågan
3. bedöma varje kandidats källtillförlitlighet och informationens konfidens separat
4. uttrycka bedömningen i procent eller tydliga konfidensnivåer enligt avsnitt 13.2
5. sortera bort kandidater med tydliga varningssignaler eller otillräckligt stöd
6. presentera de tre starkaste återstående alternativen som en topp tre-lista

Om färre än fem trovärdiga kandidater går att hitta ska MyAI använda de kandidater som finns och tydligt säga att underlaget är mindre än fem.

Topp tre-listan ska inte enbart bygga på ett enda mått. Bedömningen ska väga in relevans, källans tillförlitlighet, informationens konfidens och sådana praktiska kriterier som är viktiga för den aktuella uppgiften.

Vid prisjämförelser gäller dessutom reglerna i avsnitt 13.1 om totalpris, frakt, moms, lagerstatus, leveransmöjlighet till Sverige och säljarens trovärdighet.

### 13.4 Teknisk status för kandidatvalidering och topp tre

På utvecklingsgren finns nu en återanvändbar valideringsmotor för arbetsflödet **upp till fem kandidater → validering → topp tre**.

Motorn kräver separata poäng 0–100 för:
- relevans
- källans tillförlitlighet
- informationens konfidens

Praktisk användbarhet kan också anges och viktas när den finns. Om praktikpoäng saknas normaliseras vikterna över de dimensioner som faktiskt finns i stället för att hitta på ett värde.

Standardkonfigurationen är:
- högst 5 kandidater i valideringssteget
- topp 3 som slutresultat
- miniminivå 40 % för källtillförlitlighet, informationskonfidens och relevans
- vikter 30 % relevans, 30 % källtillförlitlighet, 30 % informationskonfidens och 10 % praktik
- mindre varningssignaler ger konfigurerbart avdrag
- kritisk varning eller uttrycklig diskvalificering sorterar bort kandidaten

Motorn behåller **källtillförlitlighet** och **informationskonfidens** som två separata värden. Den beräknar dessutom ett internt `selection_score` för sortering, men detta beskrivs uttryckligen som en heuristik och inte som sannolikheten att uppgiften är sann.

Om färre än fem kandidater finns markeras det uttryckligen. Om fler än fem skickas in utvärderas endast den konfigurerade gränsen och resultatet markerar att indata trunkerades; en framtida sökprovider ansvarar för att kandidatpoolen redan är relevansordnad innan detta steg.

Trösklar, vikter och varningsavdrag ligger i konfigurationen enligt principen om löpande finjustering.

Själva sökningen på internet är ännu inte implementerad i detta lager. Den aktuella motorn tar emot redan insamlade kandidater och är avsedd att återanvändas av framtida webb-/prisjämförelseverktyg.

Poängvalidering, bortsortering, varningsavdrag, färre-än-fem-fall, femgräns och topp-tre-sortering testas i CI.

### 13.5 Teknisk status för svensk prisjämförelse

På utvecklingsgren finns nu en prisjämförelsekärna ovanpå kandidatvalideringen i avsnitt 13.4.

För att en kandidat ska kunna rankas som ett praktiskt köpalternativ krävs som standard:
- verifierbart produktpris i SEK
- verifierad frakt till Sverige
- känd momsstatus; om moms inte ingår måste momsbeloppet vara känt
- verifierade kända extra avgifter, inklusive uttrycklig bekräftelse när beloppet är 0
- bekräftelse att säljaren levererar till Sverige
- tillräckligt verifierad lagerstatus
- källtillförlitlighet, informationskonfidens och relevans över researchmotorns trösklar

Kärnan gör **ingen tyst valutakonvertering**. Om ett pris endast finns i annan valuta diskvalificeras det tills en framtida växelkursprovider har omvandlat och verifierat beloppet.

Ett totalpris skapas endast när produktpris, frakt, moms och kända extra avgifter är tillräckligt verifierbara. Kandidater med okänd moms, okänd frakt eller oklara extra avgifter får därför inte ett låtsat komplett totalpris.

Efter researchvalideringen sorteras de godkända kandidaterna på lägsta verifierbara totalpris. Vid lika totalpris används researchmotorns interna urvalspoäng och därefter källtillförlitlighet/informationskonfidens som sekundära kriterier.

Lagerstatus `in_stock` och `limited` kan vara valbara; slut i lager eller okänd lagerstatus diskvalificerar standardmässigt kandidaten. Okänd leveranstid sänker den praktiska poängen men behöver inte ensam diskvalificera ett annars verifierat alternativ.

Logiken testas i CI för moms inkluderad/separat, okänd moms, okända avgifter, Sverigeleverans, lagerstatus, annan valuta, tillförlitlighetsfilter, färre än fem kandidater och topp tre efter lägsta kompletta totalpris.

Detta lager söker ännu inte själv på webben. Det tar emot normaliserade erbjudanden från en framtida sök-/shoppingprovider och återanvänder den centrala fem-kandidaters valideringsmotorn.

### 13.6 Teknisk status för webbsökning via SearXNG

På utvecklingsgren finns nu ett första verkligt internetverktyg `internet_search`.

Standardläget är avstängt. Konfigurationen innehåller:
- `internet.enabled=false`
- provider `searxng`
- lokal standardendpoint `http://localhost:8080`
- timeout 15 sekunder
- högst 5 sökresultat
- språk `sv-SE`
- safesearch nivå 1

Sökmodulen skickar en vanlig webbsökfråga till den konfigurerade SearXNG-instansen och normaliserar titel, URL, utdrag, sökmotor och publiceringsdatum när uppgifterna finns.

Råa sökresultat markeras uttryckligen som **icke validerade kandidater**. Webbsökningen ger alltså inte automatiskt källtillförlitlighet eller informationskonfidens bara för att ett resultat hittas.

Verktygssystemet har samtidigt utökats bakåtkompatibelt så att ett verktyg kan deklarera `pass_user_input=true`. Sådana verktyg får hela användarens fråga som argument, medan alla befintliga nollargumentsverktyg fortsätter köras som tidigare. Detta behövs för sökning och framtida parameterberoende verktyg.

SearXNG valdes som första provider eftersom den kan köras lokalt och inte kräver att MyAI hårdkodas mot en extern API-nyckel. Andra providers kan senare läggas till bakom samma modul.

Provideranrop, query-extraktion, normalisering, resultatgräns, avstängt läge och query-aware tool execution testas i CI. En verklig lokal SearXNG-instans ska senare installeras och nätverksverifieras innan internetfunktionen aktiveras i normal drift.

---

## 14. Position och lokalisering

AI:n ska i framtiden kunna känna till sin aktuella position.

Möjliga datakällor:
- GPS-modul
- telefon
- nätverksposition
- annan ansluten positioneringsenhet

AI:n ska kunna använda positionen i relevanta frågor, till exempel:
- lokalt väder
- navigation
- närliggande enheter
- lokala tjänster
- automatiska miljö- eller terminalbyten

Systemet ska skilja mellan:
- exakt GPS-position
- ungefärlig nätverksposition
- uppskattad närhet från Bluetooth

### 14.1 Teknisk status för seriell GPS-position

På utvecklingsgren finns nu verktyget `location_status` för read-only position från en seriell NMEA-GPS.

Standardläget är avstängt. Konfigurationen innehåller:
- `location.enabled=false`
- `location.source="gps_serial"`
- tom `location.serial_port`
- baudrate 9600
- timeout 1 sekund
- högst 20 NMEA-rader per läsning

GPS-lagret:
- validerar NMEA-checksumma
- tolkar GGA och RMC
- konverterar latitud/longitud till decimalgrader
- kan redovisa satellitantal, HDOP, höjd, hastighet och kurs när uppgifterna finns
- slår samman giltiga GGA/RMC-fixar
- rapporterar tydligt när ingen giltig fix finns
- gissar inte en position när mottagardata saknas eller är ogiltig

`pyserial` ligger i en separat optional dependency-fil `requirements-gps.txt`, så grundinstallationen påverkas inte när GPS inte används.

MyAI ska inte översätta HDOP till en påhittad noggrannhet i meter. Faktisk precision beror på mottagare, satellitgeometri och miljö.

NMEA-parsning, checksumma, koordinatkonvertering, seriell felhantering och resursstängning testas i CI. Verklig GPS-port, satellitfix och praktisk precision verifieras senare i den samlade hårdvarurundan när en GPS-mottagare finns.

---

## 15. Minne

AI:n ska ha både korttids- och långtidsminne.

Minnet ska kunna lagra relevanta saker som:
- användarens preferenser
- konfigurationer
- kända enheter
- verktygsinställningar
- projektstatus
- tidigare beslut
- användardefinierade regler

Minnet ska kunna användas för att slippa fråga om samma information om och om igen.

### 15.1 Automatisk bedömning av vad som bör kommas ihåg

AI:n ska själv kunna bedöma när information är tillräckligt viktig eller återkommande för att sparas i långtidsminnet.

Exempel på signaler som kan göra information minnesvärd:
- användaren nämner samma sak flera gånger
- en preferens återkommer i olika sammanhang
- informationen påverkar framtida beslut eller svar
- användaren korrigerar AI:n och korrigeringen bör gälla även framöver
- ett projektbeslut, en konfiguration eller en regel återanvänds
- informationen uttryckligen markeras av användaren som något att komma ihåg

AI:n ska kunna tänka i stil med:

> Det här har användaren nämnt flera gånger och det verkar påverka framtida svar. Det bör sparas i långtidsminnet.

Korttidsminnet ska användas för det aktuella samtalet och pågående uppgifter. Relevant information ska kunna flyttas till långtidsminnet när minnessystemet bedömer att den har ett bestående värde.

Minnet ska inte spara allt automatiskt. Tillfällig, oviktig eller känslig information ska behandlas försiktigt och minnessystemet ska använda tydliga regler för vad som är lämpligt att bevara.

### 15.2 Teknisk status för automatisk långtidsminnespolicy

På utvecklingsgren finns nu en deterministisk minnespolicy som bedömer varje
användarmeddelande innan det eventuellt förs över från korttidskontexten till
SQLite-baserat långtidsminne.

Policyn använder konfigurerbara trösklar och separerar tre utfall:
- `save` för tydliga bestående minnen
- `review` för information som verkar viktig men inte bör sparas automatiskt
- `ignore` för tillfällig, svag eller olämplig information

Starka signaler inkluderar uttryckliga "kom ihåg"-instruktioner, bestående
preferenser, återanvändbara regler och projektbeslut. Återkommande liknande
uppgifter i korttidskontexten kan höja minnesvärdet. Tydliga tidsmarkörer som
"idag", "just nu" och "den här gången" sänker det.

Automatisk lagring blockerar dessutom tydliga hemlighets- och
identifieringssignaler såsom lösenord, PIN-koder, API-nycklar, tokens,
privata nycklar, kortnummer och personnummer. Exakta dubbletter sparas inte
igen.

Standardvärdena är:
- `memory.auto_assess_enabled=true`
- `memory.auto_save_enabled=true`
- `memory.auto_save_threshold=80`
- `memory.review_threshold=55`

Bedömning, känslighetsfilter, återkomstsignal, automatisk lagring och
dubblettskydd testas i CI. Konflikthantering, ersättning av gamla minnen och
grundläggande livscykelregler är nu implementerade enligt avsnitt 15.4.

### 15.3 Minneshantering

På sikt ska det finnas tydliga regler för:
- vad som får sparas
- hur minnesvärde bedöms
- när korttidsminne flyttas till långtidsminne
- hur motstridiga uppgifter hanteras
- hur gamla uppgifter uppdateras
- hur länge information sparas
- hur den ändras
- hur den tas bort

### 15.4 Teknisk status för minneslivscykel och konflikthantering

På utvecklingsgren finns nu ett icke-destruktivt livscykellager för SQLite-minnet.

Databasen migreras bakåtkompatibelt med:
- `status=active|superseded`
- `updated_at`
- `superseded_by`
- `superseded_at`

Befintliga minnen raderas inte vid migrering. Normal sökning och normal minneslista använder endast aktiva minnen, medan full historik kan läsas separat.

När en ny minneskandidat ska sparas:
- exakta aktiva dubletter ignoreras
- ämneslikhet bedöms deterministiskt med normaliserade ord och minst två gemensamma ämnesord
- möjliga konflikter utan tydlig uppdateringssignal stoppas för `review` i stället för att skapa två aktiva motstridiga minnen
- tydliga uppdateringsfraser som `från och med nu`, `istället för` eller `new default` kan atomiskt ersätta exakt ett starkt matchande aktivt minne
- automatisk ersättning kräver som standard konfliktpoäng minst 0.85
- om flera starka kandidater matchar samtidigt sker ingen automatisk ersättning; ärendet går till granskning
- ersatt minne bevaras i historiken och pekar på det nya minnet genom `superseded_by`

Åldringsstöd finns read-only genom `MemoryStore.list_stale()`. Standard `memory.stale_after_days=0` innebär att ingen automatisk utgång eller radering sker.

Viktiga standarder:
- `memory.lifecycle_enabled=true`
- `memory.auto_supersede_explicit_updates=true`
- `memory.conflict_similarity_threshold=0.65`
- `memory.supersede_similarity_threshold=0.85`
- `memory.max_conflict_scan=200`
- `memory.stale_after_days=0`

Konfigurationen valideras fail-closed för ogiltiga trösklar och gränser. Ingen automatisk minnesradering är implementerad.

---

## 16. Modulär arkitektur

Systemet ska byggas modulärt.

### 16.1 Kamera och visuell information

AI:n ska i framtiden kunna ta emot och tolka information från en eller flera kameror utan att detta kräver stora förändringar i kärnarkitekturen.

Kamerastöd ska därför byggas som en separat modul med ett stabilt gränssnitt mot resten av systemet.

Möjliga framtida funktioner:
- ta emot stillbilder
- ta emot videoström
- beskriva vad kameran ser
- identifiera objekt
- läsa text i bild
- känna igen förändringar i en miljö
- kombinera kameradata med andra sensorer
- använda visuell information som underlag för verktyg och beslut
- på sikt stödja flera kameror eller kameraterminaler

Kärnan ska inte behöva känna till detaljer om vilken kameramodell eller vilken bildmodell som används. Kameramodulen ska i stället exponera tydliga funktioner, exempelvis:
- `camera_capture`
- `camera_status`
- `vision_analyze`
- `vision_detect_objects`
- `vision_read_text`

Det ska därmed vara möjligt att byta:
- kamera
- drivrutin
- bildmodell
- lokal eller extern visionmodell
- bildbehandlingsbibliotek

utan att skriva om dialogsystemet, minnet eller verktygsorkestreringen.

### 16.1.1 Teknisk status för kamerainventering

På utvecklingsgren finns nu ett första read-only kameralager med verktyget `camera_status`.

Verktyget kan:
- inventera Windows-kameror via närvarande PnP-enheter i klasserna Camera/Image
- inventera Linux-kameror via Video4Linux-enheter
- normalisera namn, identifierare, status och datakälla
- tydligt rapportera när ingen kamera upptäcks

Detta lager tar inga bilder och startar ingen videoström. Bildtagning, kameraval, visionmodell och objekt-/textanalys ska byggas som separata senare steg.

Parserlogiken testas i CI. Faktisk kameradetektering på Windows och senare Raspberry Pi ska verifieras i den samlade fysiska hårdvarurundan innan bildtagning byggs ovanpå den.

### 16.1.2 Teknisk status för stillbildstagning

På utvecklingsgren finns nu ett separat verktyg `camera_capture` för stillbildstagning.

Standardflödet är:
1. öppna standardkameran
2. läsa exakt en bildruta
3. spara bilden lokalt under `runtime/captures/`
4. stänga kameran direkt

Bildtagningen använder OpenCV som ett separat valbart beroende i `requirements-camera.txt`, så grundinstallationen av MyAI behöver inte bära kamerabiblioteket när kamerafunktioner inte används.

Om OpenCV saknas, kameran inte kan öppnas, ingen bildruta kan läsas eller bilden inte kan sparas ska verktyget returnera ett tydligt fel och inte påstå att en bild togs.

Bildtagning och resursstängning testas i CI med simulerad kamera. Faktisk stillbildstagning på Windows och senare Raspberry Pi ska verifieras i den samlade fysiska hårdvarurundan. Bildanalys/vision ligger fortsatt i ett separat senare lager.

### 16.1.3 Teknisk status för visionanalys

På utvecklingsgren finns nu ett separat visionlager med verktyget `vision_analyze`.

Lagret:
- analyserar den senast lokalt sparade kamerabilden
- använder en separat multimodal Ollama-modell som måste konfigureras uttryckligen
- är avstängt som standard
- skickar bilddata till den lokalt konfigurerade Ollama-endpointen som base64 i en multimodal chat-förfrågan
- vägrar analysera om ingen visionmodell är konfigurerad eller om ingen bild finns
- använder en standardprompt som uttryckligen kräver att modellen markerar osäkerhet och inte hittar på osynliga detaljer

Den vanliga textmodellen `qwen3:8b` antas inte automatiskt vara en visionmodell. Visionmodellen är därför en separat konfigurationspunkt och kan bytas utan att textdialogen ändras.

Multi-tool-routing stödjer nu även flödet **ta bild → analysera bild** i ett användarkommando. Bildtagningen körs först och visionanalysen använder därefter den senast sparade bilden.

Klientformat, bildkodning, säker standardkonfiguration och felvägar testas i CI. En verklig multimodal modell ska installeras, väljas och verifieras lokalt innan visionfunktionen aktiveras som standard.

### 16.1.4 Teknisk status för textläsning i bild

På utvecklingsgren finns nu det separata verktyget `vision_read_text` för OCR-liknande textläsning i den senast sparade kamerabilden.

Lagret:
- återanvänder den uttryckligen konfigurerade multimodala visionmodellen
- är beroende av samma säkra visionkonfiguration som `vision_analyze`
- använder en strikt prompt som ber modellen transkribera synlig text utan att gissa oläsbara bokstäver eller ord
- returnerar tydligt när vision är avstängd, ingen modell är konfigurerad eller ingen kamerabild finns
- stöder multi-tool-flödet **ta bild → läs text** i ett enda användarkommando

Textläsningen är inte en garanti för perfekt OCR. Resultatet ska behandlas som modellavläsning och osäker eller svårläst text ska inte presenteras som säker.

Routing, promptbeteende och felvägar testas i CI. Verklig textläsning ska verifieras senare tillsammans med en lokalt installerad multimodal visionmodell och verkliga kamerabilder.

### 16.1.5 Teknisk status för objektidentifiering

På utvecklingsgren finns nu det separata verktyget `vision_detect_objects` för objektidentifiering i den senast sparade kamerabilden.

Lagret:
- återanvänder samma uttryckligt konfigurerade multimodala visionmodell som övriga visionverktyg
- listar endast objekt som modellen bedömer har visuellt stöd
- kräver försiktiga konfidensnivåer hög/medel/låg i svaret
- instruerar modellen att inte gissa dolda objekt, märken, personer eller detaljer som inte går att se
- returnerar tydligt när vision är avstängd, ingen modell är konfigurerad eller ingen kamerabild finns
- stöder multi-tool-flödet **ta bild → identifiera objekt**

Objektidentifiering från en generell multimodal modell är inte samma sak som en kalibrerad detektor med verifierade bounding boxes. Resultatet ska därför behandlas som modellbaserad visuell analys och inte som exakt mätdata.

Routing, promptbeteende och felvägar testas i CI. Verklig objektidentifiering ska verifieras senare med lokal visionmodell och verkliga kamerabilder.

### 16.1.6 Teknisk status för förändringsdetektering

På utvecklingsgren finns nu verktyget `vision_detect_change` för jämförelse mellan de två senaste sparade kamerabilderna.

Lagret:
- skickar den äldre och den nyare bilden i tydlig ordning till visionmodellen
- beskriver endast tydliga visuella skillnader mellan bilderna
- instruerar modellen att inte gissa orsak, rörelse, identitet eller händelser som inte kan fastställas från två stillbilder
- kräver minst två sparade bilder
- stöder multi-tool-flödet **ta bild → jämför med föregående bild**
- återanvänder samma standardavstängda och uttryckligt konfigurerade lokala visionmodell som övriga visionverktyg

Detta är visuell jämförelse mellan stillbilder och ska inte behandlas som säker rörelsedetektering eller händelseförståelse. För verklig kontinuerlig övervakning behövs senare ett separat video-/sensorflöde.

Visionklienten har samtidigt utökats med flerbildsstöd utan att ändra det befintliga enbildsgränssnittet.

Flerbildskodning, routing, promptbeteende och felvägar testas i CI. Verklig förändringsdetektering ska verifieras senare med lokal visionmodell och verkliga kamerabilder.

### 16.1.7 Teknisk status för konfigurerbart kameraval

Stillbildslagret kan nu välja standardkamera via konfiguration i stället för att vara hårdkodat till kameraindex 0.

Konfigurationen innehåller:
- `camera.default_index` med säkert standardvärde `0`
- `camera.capture_dir` med standardvärdet `runtime/captures`

Relativa sökvägar för bildlagring löses mot projektroten. Negativa eller ogiltiga kameraindex avvisas i stället för att skickas vidare till kamerabiblioteket.

Både det vanliga `camera_capture`-verktyget och den samlade fysiska hårdvaruverifieringen använder samma kamerainställning.

Detta är ännu ett logiskt kameraindex och inte en säker beständig koppling mellan Windows PnP-ID och OpenCV-index. Praktisk mappning mellan flera fysiska kameror ska därför verifieras senare innan automatisk kameraväxling byggs.

### 16.1.8 Teknisk status för kort videoinspelning

På utvecklingsgren finns nu verktyget `camera_record_video` som spelar in ett kort lokalt videoklipp från den konfigurerade standardkameran.

Konfigurationen innehåller:
- `camera.video_dir` med standard `runtime/video`
- `camera.video_duration_seconds` med standard 5 sekunder
- `camera.video_fps` med standard 10 fps

Videomodulen:
- använder samma valda kameraindex som stillbildslagret
- skriver MP4 med OpenCV-backend
- stänger både kamera och videowriter efter inspelning
- rapporterar tydligt om kameran inte kan öppnas, första bildrutan saknas, writer inte kan öppnas eller inspelningen avbryts
- ligger separat från visionanalys och kontinuerlig livevideo

Detta är en grund för framtida videoström, inte ännu ett kontinuerligt realtidsflöde. Bildrutefrekvens, codec-stöd och faktisk inspelningslängd ska verifieras senare på fysisk Windows- och Raspberry Pi-hårdvara.

Kodvägar och resursstängning testas i CI med simulerad kamera och videowriter.

### 16.1.9 Teknisk status för representativa videobildrutor

På utvecklingsgren finns nu verktyget `camera_sample_video_frames` som väljer den senast sparade videon och plockar ut ett litet antal jämnt fördelade bildrutor över hela klippet.

Konfigurationen innehåller:
- `camera.video_frame_dir` med standard `runtime/video_frames`
- `camera.video_sample_count` med standard 5 bildrutor

Samplingslagret:
- läser videons rapporterade antal bildrutor
- väljer jämnt fördelade index från början till slut av klippet
- begränsar antalet samplingar till det faktiska antalet bildrutor
- sparar JPEG-bilder under en egen katalog per videoklipp
- stänger videoläsaren efter användning
- rapporterar tydligt om videon saknas, inte kan öppnas, saknar användbart frame count eller om en vald bildruta inte kan läsas/sparas

Multi-tool-routing stödjer också flödet **spela in video → plocka ut representativa bildrutor** i ett användarkommando.

Detta lager gör ingen visuell tolkning. Det skapar ett kontrollerat och resurssnålt underlag som senare kan skickas till visionmodellen i stället för att analysera varje videobildruta.

Urval, filhantering, routing och felvägar testas i CI. Fysisk verifiering av frame count, seek-beteende och bildkvalitet sparas till den samlade kamerarundan.

### 16.1.10 Teknisk status för analys av samplad video

På utvecklingsgren finns nu verktyget `vision_analyze_video`.

Standardflödet är:
1. välj den senast sparade videon
2. plocka ut det konfigurerade antalet representativa bildrutor
3. begränsa analysen till högst åtta jämnt fördelade bildrutor
4. skicka bildrutorna i kronologisk ordning till den konfigurerade lokala multimodala visionmodellen
5. sammanfatta vad som faktiskt stöds av de samplade bilderna

Prompten förbjuder modellen att påstå att den har sett varje bildruta eller att gissa ljud, identitet, orsak, exakt rörelse eller händelser som inte kan fastställas från urvalet.

Multi-tool-routing stödjer även **spela in video → analysera video**. Analysverktyget gör då sin egen representativa sampling av den senast inspelade videon.

Detta är inte kontinuerlig videoanalys. Ett kort urval kan missa händelser mellan samplingspunkterna. Resultatet ska därför behandlas som en försiktig sammanfattning av representativa frames, inte som en fullständig tidslinje.

Samplingsfel, frame-begränsning, flerbildsanrop, routing och promptbeteende testas i CI. Verklig videokvalitet och visionmodellens träffsäkerhet ska verifieras senare med fysisk kamera och lokal multimodal modell.

### 16.1.11 Teknisk status för begränsat kamerastream-lager

På utvecklingsgren finns nu ett kontrollerat streamlager med verktyget `camera_stream_status`.

Standardläget är avstängt genom `camera.stream_enabled=false`. När funktionen aktiveras gäller dessutom hårda säkerhets- och resursgränser:
- `camera.stream_duration_seconds` med standard 5 sekunder och maximal tillåten längd 60 sekunder
- `camera.stream_fps` med standard 2 fps och maximal tillåten nivå 30 fps
- `camera.stream_max_frames` med standard 10 och absolut max 300 frames

Streamlagret:
- använder samma konfigurerade kameraindex som övriga kamerafunktioner
- öppnar kameran endast under den begränsade sessionen
- kan lämna varje frame till en separat callback för framtida analys
- stänger alltid kameran efter sessionen eller vid fel
- startar ingen bakgrundstråd och ingen obegränsad kontinuerlig övervakning
- skriver inte automatiskt streamens frames till disk

Detta är ett fundament för senare livevideo och realtidsanalys, inte ännu en permanent kamerabevakning. Den samlade fysiska hårdvaruverifieringen innehåller ett kort explicit stream-test som tillfälligt aktiverar funktionen utan att ändra den sparade konfigurationen.

Gränsvalidering, frameflöde, callback, felvägar och resursstängning testas i CI. Faktisk stabilitet, timing, kameraindex och belastning ska verifieras senare på Windows och Raspberry Pi.

### 16.1.12 Teknisk status för begränsad live-vision

På utvecklingsgren finns nu verktyget `vision_analyze_live`, byggt ovanpå det begränsade kamerastream-lagret.

Funktionen:
- kräver att både vision och kamerastream uttryckligen är aktiverade
- begränsar analysen till högst sex liveframes per körning
- JPEG-kodar frames direkt i minnet
- skickar bilddata direkt till den konfigurerade lokala visionmodellen utan automatisk lagring av liveframes på disk
- instruerar modellen att inte låtsas att den har sett en obruten videoström mellan de analyserade framesen
- förbjuder gissningar om ljud, identitet, avsikt, orsak och händelser som inte kan styrkas visuellt

`VisionClient` har samtidigt fått stöd för in-memory-bilddata utöver befintliga filbaserade bilder.

Detta är fortfarande en kort, begränsad analysession och inte permanent realtidsbevakning. Både `vision.enabled` och `camera.stream_enabled` är avstängda som standard.

In-memory-kodning, framebegränsning, routing, felvägar och promptbeteende testas i CI. Faktisk latens, GPU/RAM-belastning, kamerastabilitet och kvalitet från en lokal multimodal modell ska verifieras senare i den samlade fysiska hårdvarurundan.

### 16.2 Multimodal utbyggbarhet

Arkitekturen ska förberedas för att AI:n på sikt kan arbeta med flera typer av information samtidigt, exempelvis:
- text
- tal
- ljud
- bilder
- video
- sensordata
- position
- systemdata

Varje sådan informationskälla ska så långt som möjligt anslutas genom separata moduler med standardiserade in- och utdata.

Detta ska göra det möjligt att bygga ut systemet stegvis utan stora eller riskfyllda ändringar i grundkoden.


Kärnan ska i första hand ansvara för:
- dialog
- verktygsval
- minne
- planering
- säkerhet
- svarsgenerering

Separata moduler ska ansvara för exempelvis:
- systemstatus
- Bluetooth
- USB
- GPS
- väder
- Excel
- filsystem
- röst
- hårdvara
- internet

Det ska gå att lägga till nya moduler utan att behöva bygga om hela systemet.

---

## 17. Felhantering

Om ett verktyg misslyckas ska AI:n inte låtsas att det fungerade.

Den ska kunna säga:
- vilket verktyg som misslyckades
- varför, om orsaken är känd
- vilken information som saknas
- om ett alternativt verktyg kan användas

Fel ska loggas så att de går att felsöka.

### 17.1 Teknisk status för strukturerad felloggning

På utvecklingsgren finns nu ett gemensamt best-effort-lager för fel som uppstår när MyAI laddar moduler eller kör verktyg.

Lagret:
- skriver strukturerade JSONL-poster med tid, händelsetyp, komponent, felklass och begränsat felmeddelande
- återanvänder projektets befintliga roterande JSONL-logik så loggfiler inte kan växa obegränsat
- sparar inte rå användarfråga eller prompt i felloggen
- normaliserar radbrytningar och begränsar felmeddelandets längd
- är konfigurerbart genom `error_logging.enabled`, `error_logging.path` och `error_logging.max_message_chars`
- är fail-safe: om själva felloggningen misslyckas får detta inte maskera det ursprungliga verktygsfelet eller stoppa övriga verktyg
- ändrar inte befintligt tool-resultatformat; användaren får fortfarande ett tydligt felresultat för det misslyckade verktyget medan andra verktyg kan fortsätta

Standardläget är aktiverad lokal felloggning till `runtime/errors.jsonl`. Filen ligger under runtime och ska inte versionshanteras.

Både modulimportfel och tool-körfel kopplas till fellagret. Konfiguration, truncering, loggfel och multi-tool-beteende testas i CI.

### 17.2 Read-only diagnostik av senaste fel

På utvecklingsgren finns nu verktyget `myai_recent_errors` för att läsa de senaste strukturerade MyAI-felen genom naturligt språk, exempelvis:

> Vilka fel har MyAI haft?

Verktyget:
- läser endast felloggen och ändrar eller raderar ingenting
- läser aktuell JSONL-fil samt roterade backupfiler i korrekt nyast-först-ordning
- använder ett konfigurerbart standardantal genom `error_logging.recent_limit`
- har en absolut maxgräns på 50 poster per anrop
- ignorerar trasiga eller ogiltiga JSON-rader utan att hela diagnostiken faller
- återanvänder den redan begränsade feltexten och exponerar inte rå användarfråga eller prompt
- rapporterar tydligt när felloggning är avstängd eller när inga fel finns

Ingen funktion för att rensa, kvittera eller ändra felloggen exponeras genom verktyget.

---

## 18. Säkerhet

AI:n ska kunna ha stor tillgång till den lokala datorn eller Raspberry Pi, men detta kräver tydliga säkerhetsnivåer.

Exempel på åtgärder som bör kräva extra kontroll:
- radera filer
- skriva över viktig kod
- ändra systemkonfiguration
- installera systempaket
- köra kommandon med höga rättigheter
- ändra nätverksinställningar
- modifiera säkerhetsinställningar
- styra fysisk hårdvara som kan orsaka skada

AI:n ska kunna göra mycket själv, men autonomin ska vara kontrollerad och spårbar.

### 18.1 Teknisk status för audit-logg och spårbara skrivåtgärder

På utvecklingsgren finns nu ett separat strukturerat audit-lager för skrivande och säkerhetsrelevanta åtgärder.

Auditlagret:
- skriver JSONL med tid, åtgärd, komponent, utfall, mål och begränsad metadata
- skiljer på `attempt`, `success`, `denied` och `failed`
- återanvänder projektets roterande JSONL-lager
- sparar inte rå användarprompt, filinnehåll, Excel-cellvärden eller selfdev-godkännandefraser
- har `audit_logging.require_for_writes=true` som säker standard
- blockerar skrivåtgärden innan mutation om obligatorisk audit inte kan skriva sin `attempt`-post
- behandlar efterföljande resultatloggning som best-effort så ett redan genomfört skrivresultat inte döljs av sekundärt loggfel

Audit är inkopplat i:
- allmän workspace-textskrivning
- Excel-create, sheet-create, append och celländring
- selfdev promotion
- selfdev rollback

För selfdev loggas endast session-/promotion-ID och antal ändrade/tillagda filer; själva approval-fråsen loggas aldrig.

Read-only verktyget `myai_audit_status` visar högst ett konfigurerat antal senaste audit-händelser, med absolut max 50 poster. Det kan inte rensa eller ändra auditloggen.

Standardvärden:
- `audit_logging.enabled=true`
- `audit_logging.require_for_writes=true`
- `audit_logging.path=runtime/audit.jsonl`
- `audit_logging.max_detail_chars=200`
- `audit_logging.recent_limit=20`

Fail-closed configvalidering blockerar bland annat obligatorisk men avstängd audit, saknad loggsökväg och ogiltiga storleksgränser.

---

## 19. Versionshantering

GitHub eller lokal Git ska användas för projektets källkod.

Mål:
- varje fungerande version ska kunna sparas
- förändringar ska kunna granskas
- felaktiga förändringar ska kunna återställas
- utveckling och aktiv version ska hållas separerade när det behövs

Känsliga filer ska inte laddas upp till GitHub.

Exempel som normalt ska ligga i `.gitignore`:
- `.env`
- API-nycklar
- lösenord
- `memory.db`
- privata loggar
- cachefiler
- `__pycache__/`

---

## 20. Utvecklingsprincip

Utvecklingen ska ske stegvis.

Varje ny funktion ska så långt det är praktiskt möjligt:
1. byggas som en separat modul
2. testas isolerat
3. kopplas till verktygssystemet
4. testas genom naturligt språk
5. dokumenteras
6. versionshanteras

Fungerande moduler ska inte ändras i onödan när nya funktioner byggs.

### 20.1 Löpande finjustering

MyAI ska kunna finjusteras stegvis efter praktisk användning. Grundarkitekturen ska därför skilja så långt som möjligt mellan kärnkod och sådant som kan justeras genom konfiguration.

Exempel på sådant som bör kunna ändras utan stora ingrepp i kärnan:
- beteenderegler
- tröskelvärden
- säkerhetsnivåer
- konfidensgränser
- minnesregler
- prioritering mellan verktyg
- hur svar presenteras
- när systemet ska fråga om förtydligande
- vilka moduler som ska användas i olika situationer

Om användaren märker att assistenten beter sig olämpligt eller inkonsekvent ska systemet kunna justeras med små, kontrollerade ändringar och testas innan större arkitekturändringar övervägs.

Inställningar och regler bör så långt som möjligt vara dokumenterade, versionshanterade och möjliga att återställa.

---

## 21. Nuvarande prioritet och teknisk status

Multi-tool-stödet är implementerat och verifierat med automatiska tester.

Den pågående utvecklingsgrenen innehåller nu:
- dynamisk laddning av modulära verktyg
- stöd för att välja och köra flera verktyg för samma fråga
- separat `core/tool_manager.py`
- separat konfigurationsladdning via `config/settings.json`
- separat SQLite-baserat långtidsminne via `core/memory.py`
- gemensam Ollama-klient via `core/ollama_client.py`
- återanvändbar AI-kärna via `core/assistant.py`
- konfigurerbart korttidsminne för pågående samtal
- möjlighet att rensa samtalets korttidsminne
- automatiska tester via GitHub Actions
- USB-status som första nya fristående hårdvarumodul efter systemverktygen
- automatisk hårdvaruövervakning på staplad utvecklingsgren
- persistent register för kända och okända enheter
- samlat guidat hårdvaruvalideringsskript för Windows-testning
- separat BLE/RSSI-närhetslager med grov avståndsbedömning
- Bluetooth RSSI-steg i den samlade fysiska hårdvaruverifieringen
- konfigurerbar policy för betrodda terminaler med RSSI-hysteres
- explicit godkännandeflöde för nya enheter med persistent pending/approved/rejected-status
- Raspberry Pi-systemstatus för CPU, RAM, lagring, temperatur, spänning och throttling
- Raspberry Pi GPIO-referens med I2C/SPI/UART-mappning och konservativ elsäkerhetskontroll
- read-only Raspberry Pi-inventering av GPIO-, I2C-, SPI- och UART-gränssnitt
- read-only Raspberry Pi-diagnostik för nätverk, processer, systemd-tjänster och systemloggar
- read-only Raspberry Pi-strömtelemetri via Linux hwmon utan uppskattade mätvärden
- read-only inventering av kernel-registrerade I2C- och SPI-enheter via Linux sysfs
- read-only kamerainventering för Windows PnP och Linux Video4Linux
- separat stillbildstagning till lokala runtime/captures med omedelbar kamerastängning
- separat, konfigurerbart och standardavstängt visionlager för analys av senaste kamerabild
- separat OCR/textläsningslager för senaste kamerabild med no-guess-prompt
- separat objektidentifieringslager med försiktiga konfidensnivåer och no-guess-regler
- flerbildsstöd och separat förändringsdetektering mellan de två senaste kamerabilderna
- konfigurerbart standardkameraindex och capture-katalog för stillbildstagning
- separat kort videoinspelning med konfigurerbar längd, fps och lokal videokatalog
- representativ sampling och försiktig multimodal analys av videobildrutor
- standardavstängt och hårt begränsat kamerastream-lager som grund för senare livevideo
- standardavstängd begränsad live-vision med in-memory-frames och utan automatisk disksparning
- standardavstängd seriell NMEA-GPS med checksummevalidering och no-guess-position
- konfigurerbar fem-kandidaters valideringsmotor med separata käll-/informationspoäng och topp-tre-urval
- svensk prisjämförelsekärna med verifierbart totalpris, Sverigeleverans, lagerfilter och topp tre billigaste godkända alternativ
- standardavstängd lokal-först webbsökning via konfigurerbar SearXNG-provider och query-aware verktygskörning
- säker publik webbsideshämtning med blockering av privata/lokala IP-adresser, redirect-kontroll, innehållstypfilter och storleksgräns
- sidbaserad källgranskning med metadata-, transparens- och evidenssignaler samt konservativt begränsade heuristiska käll-/informationspoäng
- sammanhängande researchflöde som söker upp till fem kandidater, hämtar och verifierar sidor, upptäcker tydliga numeriska motsägelser mellan oberoende domäner och rangordnar topp tre
- representativ bildrutssampling från senaste videon som grund för resurssnål videoanalys
- sandboxad lokal filyta med säkra textfilverktyg och standardavstängd skrivning
- Excel-stöd för skapa/läsa/rader/celler/blad med separat standardavstängd skrivning
- automatisk långtidsminnespolicy med save/review/ignore, känslighetsfilter och dubblettskydd
- komplett standardavstängd lokal röstpipeline med VAD, STT-konsensus, TTS, avbrott, handsfree, eko-skydd och högriskbekräftelse
- terminalkommandon för lazy röstsession och handsfree-läge utan ljudinitiering vid vanlig start
- komplett standardavstängt terminalhandoff-lager med fler-skanningsbekräftelse, RSSI-hysteres och fail-closed-policy
- valbar BLE GATT-connector som endast arbetar med uttryckligt betrodda terminaler och verifierar konfigurerad service UUID
- separata lokala verifieringsskript för terminal-RSSI/handoff och explicit GATT connect/disconnect

De fem ursprungliga systemverktygen ska fortsatt fungera:
- `gpu_status`
- `cpu_status`
- `ram_status`
- `temperature_status`
- `disk_status`

Därutöver finns:
- `usb_status`

### 21.1 Pågående VENTUNO Q-migrering

Efter pre-hardware-checkpointen har MyAI:s primära målhårdvara ändrats till Arduino VENTUNO Q med Qualcomm Dragonwing IQ-8275 och 16 GB RAM. Raspberry Pi-lagren behålls som alternativa Linux-/GPIO-moduler men är inte längre huvudmålet.

Följande VENTUNO-anpassning är nu implementerad på separat utvecklingsgren:

- Ollama är fortsatt standardprovider i Windows-utvecklingsmiljön
- provider-neutralt LLM-lager med `llm.provider=ollama|geniex`
- separat GenieX-klient mot det lokala OpenAI-kompatibla API:t
- planerad normalmodell `ai-hub-models/Qwen3-4B-Instruct-2507`
- tokenstreaming för både Ollama och GenieX
- provider-neutral `MyAICore.respond_stream()` som fortfarande sparar komplett svar och samtalskontext
- meningsbuffrad streaming-TTS så generering och uppläsning kan överlappa utan token-för-token-tal
- avbrott av pågående streaming-TTS med tömning av väntande talkö
- separat runtime-profil `config/profiles/ventuno_q.json`
- profilval genom `MYAI_SETTINGS` utan manuell redigering av standardkonfigurationen
- launcher `scripts/start_ventuno.sh`
- provider-neutral visionfabrik med befintlig Ollama-vision och ny GenieX-VLM-klient
- OpenAI-kompatibla multimodala GenieX-anrop med base64-bilder för stillbild, OCR, objekt, förändring, video och live-vision
- planerad VENTUNO-VLM `qualcomm/Qwen3-VL-4B-Instruct`, fortfarande avstängd tills fysisk verifiering
- resurs-handoff för röst där VENTUNO-profilen kan frigöra mikrofonströmmen före tung AI-inference och återstarta den efteråt
- VENTUNO-profilens handoff-delay är 1,5 sekunder; Windows-standard är fortsatt avstängd handoff
- separat, lazy och fail-closed STM32/RPC-klient ovanpå officiella `arduino-router-bridge`
- RPC-skrivning är avstängd som standard och varje läs-/skrivmetod måste finnas i separat allowlist
- `ventuno_rpc_status` kan visa policy/status utan att ansluta till STM32
- `requirements-ventuno.txt` håller VENTUNO-specifika beroenden separerade från grundinstallationen
- read-only `scripts/ventuno_preflight.py` kontrollerar Linux ARM64, GenieX-provider/CLI, lokal endpoint, modellkonfiguration, Router Bridge, Unix-socket och RPC-skrivskydd utan inference eller fysisk styrning
- systemverktygen har gjorts mer plattformsneutrala: diskstatus använder filsystemet där MyAI ligger och temperatur kan falla tillbaka till Linux thermal sysfs
- befintliga Windows/Ollama-, minnes-, verktygs-, Bluetooth-, fil-, Excel- och säkerhetslager är fortsatt återanvända

All ovanstående mjukvarulogik verifieras med automatiska tester och mockade providers. CI-resultat får inte beskrivas som verifiering av Dragonwing-NPU, QAIRT, VENTUNO-kamera, STM32, verklig ljudpipeline eller fysisk I/O.

### 21.2 Kvarvarande fysisk VENTUNO-verifiering

När VENTUNO Q finns tillgänglig ska nästa verifieringsrunda ske på målhårdvaran i denna ordning:

1. installera och versionslåsa den VENTUNO/Qualcomm-mjukvarustack som faktiskt används
2. verifiera `geniex` och köra read-only `scripts/ventuno_preflight.py`
3. hämta och verifiera den valda Qwen3-4B-bundlen för IQ-8275
4. starta GenieX lokalt och mäta kallstart, TTFT, tokens/s, RAM och temperatur
5. verifiera tokenstreaming och meningsbuffrad TTS
6. verifiera mikrofon/VAD/STT och den 1,5 sekunders resurs-handoff som används innan LLM/VLM väcks
7. välja och verifiera dokumenterad Qualcomm-/Arduino-accelererad Whisper-backend; tills dess är `faster-whisper` endast en fallback
8. verifiera VLM med riktig kamera och därefter stillbild, OCR, objekt, förändring, video och begränsad live-vision
9. verifiera Arduino Router-socket och endast en uttryckligt allowlistad read-only STM32-RPC-metod
10. aktivera fysisk RPC-skrivning först efter separat säkerhetsgranskning, MCU-watchdog och explicita allowlists
11. verifiera Bluetooth, Wi-Fi, USB, GPS och övrig faktisk kringutrustning
12. genomföra ett minst 72 timmar långt stabilitetstest med modellbyten, röst, VLM, SQLite, nätverk, STM32-RPC, omstarter, temperatur och återhämtning efter fel

Utvecklingen får fortsätta mjukvarumässigt fram till den punkt där nästa steg kräver verklig VENTUNO-hårdvara, men sådana steg ska då markeras som uppskjutna i stället för simulerade som godkända.

VENTUNO-providerbytet ska inte mergas till `main` som permanent standard förrän grundläggande fysisk GenieX/QAIRT-verifiering är genomförd. Ollama förblir därför säker standard i huvudkonfigurationen under migrationsfasen.


### 21.3 Paus/checkpoint 2026-10-04

Arbetet pausas här på användarens begäran.

GitHub-läge vid pausen:
- aktiv utvecklingsgren: `dev/ventuno-q-provider`
- draft-PR: **#85 – Begin Arduino VENTUNO Q / GenieX migration**
- senast verifierade kodcommit före denna dokumentationscheckpoint: `cbcf661c147bdeb76701605fd18b6f94d545f638`
- GitHub Actions-run `37213237747` för commit `cbcf661c` är **success**
- Ollama är fortfarande säker standardprovider i Windows-konfigurationen
- VENTUNO Q / GenieX är förberett genom separat profil och är inte permanent aktiverat i huvudkonfigurationen
- inga fysiska VENTUNO Q-tester har genomförts ännu

Senast färdigställda kodpunkt:
- röst-state-machine har korrigerats så ordningen är **fånga tal → stoppa live-mikrofon → STT → frigör eventuell accelererad STT-provider → 1,5 s handoff → LLM/VLM → återstarta mikrofon**
- 1,5-sekunders väntan ligger alltså mellan STT och LLM/VLM, inte före transkriberingen
- read-only STM32-bridge-skelett finns med endast `myai_ping`, `myai_uptime_ms` och `myai_mcu_status`
- skrivande STM32-RPC är fortfarande avstängt och write-allowlisten är tom
- VENTUNO preflight, GenieX LLM/VLM-provider, streaming, meningsbuffrad TTS och Linux-portabla systemverktyg är implementerade

Exakt återstartspunkt:
1. kontrollera att senaste GitHub Actions för denna checkpoint fortfarande är grön
2. fortsätt från VENTUNO-röst/STT-lagret
3. hardkoda inte ett Qualcomm-/Arduino-accelererat Whisper-API förrän det finns en dokumenterad och verifierbar backend för den faktiska VENTUNO-mjukvarustacken
4. behåll `faster-whisper` som fallback tills fysisk hårdvara finns
5. därefter fortsätt endast med mjukvaruarbete som inte kräver påhittad NPU/STM32-hårdvaruverifiering
6. när VENTUNO Q finns, börja med `scripts/ventuno_preflight.py` och följ den fysiska verifieringsordningen i avsnitt 21.2



### 21.4 Återupptaget arbete 2026-10-05

Arbetet återupptogs från checkpointen i avsnitt 21.3 och följande mjukvarulager har lagts till:

- `faster-whisper` kan nu frivilligt frigöra sin laddade modell efter STT och före LLM/VLM
- STT-resursfrigöring styrs av `voice.release_stt_before_model` och är avstängd i Windows-standardprofilen
- VENTUNO-profilen aktiverar resursfrigöring och behåller `faster-whisper` som fungerande fallback tills en accelererad ASR-provider är verifierad
- primär och backup-STT kan nu använda olika providers genom `stt_provider` respektive `backup_stt_provider`
- detta förbereder VENTUNO för en framtida Qualcomm/App Lab Whisper-provider som primär och `faster-whisper` som reserv utan ändringar i resten av röstpipen
- ett nytt `ResilientLLMClient` kan ge lokal modellfallback om primär LLM-backend får ett återhämtningsbart runtime-/anslutnings-/modellsvarsfel
- LLM-fallback är avstängd i både standard- och VENTUNO-profil tills en fysisk reservmodell är verifierad
- streaming-fallback får endast ske innan första primärtoken har skickats; en påbörjad primärström får aldrig blandas med reservmodellens svar
- programmeringsfel som `TypeError` ska inte döljas av fallback
- varje MyAI-svar kan bära intern `llm_runtime`-metadata som visar om primär eller fallback-backend användes
- GenieX supervisor/watchdog använder read-only `GET /v1/models` för readiness utan token-generering; VENTUNO-profilen har health-monitorering på men automatisk restart av, tomt restart-kommando, feltröskel, cooldown och maxförsök
- naturligt språk kan endast anropa `geniex_status`; ingen restart-action exponeras som MyAI-verktyg
- watchdoggen skriver senaste GenieX-läge atomiskt till `runtime/geniex_health.json`; MyAI skriver efter varje svar en kombinerad backendstatus till `runtime/myai_health.json`
- hälsoklassificeringen är `healthy`, `degraded`, `unhealthy` eller `unknown`; gamla snapshots behandlas som stale/unknown i stället för aktuell status
- varje svar innehåller intern `llm_runtime`- och `health`-metadata, och en kort read-only hälsosammanfattning läggs i systemkontexten så modellen känner till degraderat/fallbackläge
- health-aware backend recovery är implementerad med hysteresis: tre felkontroller kan välja reservbackend och tre nya lyckade kontroller efter fallbackaktivering krävs innan primärbackend återställs
- stale/saknad watchdogstatus får inte tvinga backendbyte; historiska success-streaks före degradering får inte användas för omedelbar återgång
- VENTUNO-profilen förbereder health-aware routing men själva fallbacken är fortsatt avstängd och reservmodell tom tills kompatibel fysisk modell är verifierad
- hälsostatus rapporterar nu både GenieX failure streak, recovery success streak och LLM-routingorsak
- fail-closed konfigurationsvalidering finns genom `core/config_validation.py` och `scripts/validate_config.py`; VENTUNO-startscript validerar innan start
- JSONL-loggar för watchdog/stabilitet har begränsad storlek och backup-rotation så långkörningar inte kan växa obegränsat
- headless deployment är separerad från interaktiva `mail.py`: `scripts/ventuno_runtime.py` hanterar lifecycle, heartbeat och ren SIGTERM/SIGINT-shutdown
- VENTUNO-profilen kräver fysisk preflight före normal headless start
- systemd-enheter genereras endast till `runtime/systemd/`; ingen installation eller `systemctl` sker automatiskt; process-crash-recovery är begränsad med `Restart=on-failure` och start-limit
- naturligt språk kan läsa detta genom `myai_health_status`, men verktyget kan inte trigga restart eller fysisk styrning
- `scripts/geniex_watchdog.py` kan senare köras separat och loggar watchdog-händelser till JSONL; automatisk restart får inte aktiveras förrän den riktiga VENTUNO-installationens tjänstehantering har verifierats
- `scripts/ventuno_stability_test.py` är förberett för den senare 72-timmarskörningen och loggar first-token-latens, total svarstid, primär/fallback-backend, CPU, RAM, disk och temperatur i JSONL utan STM32/GPIO-skrivningar
- VENTUNO preflight kontrollerar nu även `geniex --version` och `geniex model list`
- om den konfigurerade Qwen-modellen inte finns i chipsetets kompatibla GenieX-lista blir preflight blockerande FAIL
- om modellistan inte kan läsas blir kontrollen WARN i stället för att felaktigt påstå kompatibilitet
- den officiella Arduino VENTUNO Q-guiden använder Whisper Small (quantized) genom App Lab ASR-bricken, men MyAI hårdkodar inte ett odokumenterat fristående Brick-API innan den faktiska VENTUNO-mjukvarustacken kan verifieras

Nästa mjukvarumässiga fokus är robust runtime-/stabilitetsövervakning inför den senare 72-timmarskörningen, samtidigt som fysisk NPU/ASR/VLM/RPC-verifiering fortsatt skjuts upp tills VENTUNO Q finns tillgänglig.


### 21.5 Säker selfdev-staging, verifiering och rollback

Det tidigare stora mjukvarugapet kring säker självkodning har nu fått ett första fail-closed implementationslager.

Implementerat:
- selfdev är avstängt som standard genom separat `selfdev.enabled=false`
- promotion har en andra separat spärr `selfdev.promotion_enabled=false`
- kandidatkod kopieras till isolerad staging under `runtime/selfdev/<session>/workspace`; aktiv kod skrivs inte under förslagsfasen
- endast explicit tillåtna text-/källkodsytor och filtyper kopieras; `.git`, `runtime`, virtuella miljöer, symlänkar, traversal och binära/otillåtna suffix blockeras
- sessionen sparar SHA-256-baseline och upptäcker source drift
- varje staging-skrivning genom API:t ogiltigförklarar tidigare verifiering
- `scripts/selfdev_review.py` visar exakt unified diff, verifieringsstatus och source drift före promotion
- verifiering körs endast genom Bubblewrap; saknas `bwrap` vägrar systemet köra i stället för att exekvera kandidatkod osandboxat på host
- verifieringsmiljön unshare:ar namespaces, saknar nätverk, får minimal syntetisk `/dev`, read-only systembinds och endast staging-workspacen som skrivbar projektarea
- verifieringen kör ett fast `python -m pytest -q` och binder verifieringsresultatet till staging-manifestets hash
- filradering är inte tillåten för promotion i denna fas
- promotion kräver passing Bubblewrap-verifiering, oförändrad staging, ingen source drift, båda config-spärrarna och exakt manuell fras `PROMOTE <session-id>`
- rollback-backup skapas innan aktiv filskrivning; filersättning sker atomiskt och delvis misslyckad promotion återställs
- rollback kräver exakt manuell fras `ROLLBACK <session-id> <promotion-id>`
- rollback vägrar skriva över filer som ändrats efter promotion och tar bort filer som promotionen själv lade till
- selfdev/promotion/rollback exponeras inte som naturliga MyAI-verktyg, har ingen fri shell-exekvering och gör inga automatiska Git-commits/pushar

Detta är ett staging-/promotion-säkerhetslager, inte ett generellt bevis på att AI-genererad kod är säker. Fysisk VENTUNO-I/O och säkerhetskritisk MCU-funktionalitet ska även fortsättningsvis hållas utanför autonom promotion.


### 21.6 Paus/checkpoint 2026-10-05

Arbetet pausas här på användarens begäran.

GitHub-läge vid pausen:
- aktiv utvecklingsgren: `dev/ventuno-q-provider`
- draft-PR: **#85 – Begin Arduino VENTUNO Q / GenieX migration**
- senast fullt verifierade kod-/dokumentationscommit före denna checkpoint: `4a2af09d72501acd1cd89c4ff8bd9f63bb9e6cb4`
- GitHub Actions-runs `37263678721` och `37263682476` för `4a2af09d` är **success**
- inga fysiska VENTUNO Q-tester har genomförts; CI-resultat gäller endast mjukvarulagret

Senast färdigställda mjukvaruläge:
- fail-closed config-validering finns och VENTUNO-start vägrar starta på blockerande profilfel
- watchdog- och stabilitets-JSONL har begränsad storlek och roterande backups
- headless VENTUNO-runtime, heartbeat och ren shutdown finns
- systemd-enheter genereras endast till staging under `runtime/systemd/`; inget installeras eller aktiveras automatiskt
- process-crash-recovery är begränsad och separerad från GenieX supervisor/restart-policy
- intern MyAI-hälsa, GenieX watchdog, health-aware primary/fallback-routing och recovery-hysteresis är implementerade
- fallbackmodell är fortfarande inte aktiverad eller vald för fysisk VENTUNO
- säker selfdev-staging finns med default-off, Bubblewrap-only verifiering, diff-review, hashbunden verifiering, manuell promotion och manuell rollback
- selfdev kan inte automatiskt köra fri shell, göra Git commit/push, skriva fysisk VENTUNO-I/O eller exponeras som naturligt MyAI-verktyg
- promotion och rollback kräver exakta manuella fraser och skydd mot source drift/out-of-band-förändringar

Exakt återstartspunkt:
1. kontrollera att branch-head och GitHub Actions fortfarande är gröna
2. fortsätt från commit `4a2af09d72501acd1cd89c4ff8bd9f63bb9e6cb4` plus denna checkpointcommit
3. behåll all fysisk VENTUNO/NPU/ASR/VLM/STM32-verifiering uppskjuten tills kortet finns
4. välj nästa rent mjukvarumässiga steg utan att försvaga selfdev-, RPC-, restart- eller config-spärrarna
5. när VENTUNO Q finns: börja med config-validering och `scripts/ventuno_preflight.py`, därefter följs avsnitt 21.2


### 21.7 Återupptaget arbete 2026-10-05 – deployment-/versionslåsning

Nästa rent mjukvarumässiga steg efter checkpointen i avsnitt 21.6 är nu implementerat på separat feature-gren och verifierat i CI.

Implementerat:
- nytt read-only lager i `core/deployment_lock.py` för att samla faktiskt observerbara mjukvaruidentifierare utan AI-inference eller fysisk styrning
- identifierare omfattar operativsystem/arkitektur, Python-version, `geniex --version`, installerad `arduino-router-bridge`-version, SHA-256 för `requirements-ventuno.txt` och konfigurerad LLM-modell
- `scripts/ventuno_version_lock.py capture` skapar endast en olåst kandidat under `runtime/`; kandidaten får `locked=false` och kan därför inte användas som ett godkänt lås av misstag
- `scripts/ventuno_version_lock.py verify` jämför den observerade stacken mot ett manuellt granskat lås och failar vid versionsavvikelse
- `deployment_lock.required=false` är fortsatt säker standard både globalt och i VENTUNO-profilen
- när `deployment_lock.required=true` blir ett giltigt `deployment_lock.lock_path` obligatoriskt och VENTUNO-preflight blockerar start vid saknat, olåst, ofullständigt eller avvikande lås
- inget permanent `config/ventuno_stack_lock.json` har skapats ännu, eftersom faktiska GenieX/Qualcomm/Python-miljöversioner ska läsas från den fysiska VENTUNO Q och inte gissas
- inga paket installeras, inga systemtjänster ändras och ingen STM32/GPIO/NPU-skrivning sker av versionslåslagret

Automatisk verifiering:
- kodhead före denna dokumentationsuppdatering: `93174fbd43da3cadb0f07de755081974f9001a90`
- GitHub Actions-run `37264558181` är **success**
- både Python-kompilering och full pytest-svit passerade

När fysisk VENTUNO Q finns ska avsnitt 21.2 steg 1 använda detta lager för att fånga den verkliga installerade stacken, manuellt granska den och först därefter aktivera ett permanent versionslås. Fram till dess ska versionslåset förbli avstängt och får inte fyllas med antagna Qualcomm-/GenieX-versioner.


### 21.8 Paus/checkpoint 2026-10-05 – efter deployment-/versionslåsning

Arbetet pausas här på användarens begäran.

GitHub-läge vid pausen:
- aktiv utvecklingsgren: `dev/ventuno-q-provider`
- draft-PR: **#85 – Begin Arduino VENTUNO Q / GenieX migration**
- aktuell branch-head före denna checkpoint: `0f6553d8b35f32eaaba77b11d8d9c2c29214e073`
- GitHub Actions-run `37264670343` för denna head är **success**
- `main` är fortsatt orörd
- inga fysiska VENTUNO Q-/NPU-/ASR-/VLM-/STM32-tester har genomförts; CI-resultat gäller mjukvarulagret

Senast färdigställda mjukvaruläge:
- fail-closed deployment-/versionslåsning är implementerad för VENTUNO
- `core/deployment_lock.py` samlar endast faktiskt observerbara mjukvaruidentifierare
- `scripts/ventuno_version_lock.py capture` skapar en olåst kandidat under `runtime/`
- capture-resultatet får `locked=false` och kan inte av misstag räknas som ett godkänt permanent lås
- `verify` jämför observerad stack mot ett manuellt granskat lås och failar vid avvikelse
- `deployment_lock.required=false` är fortsatt säker standard
- VENTUNO-preflight blockerar när låsning senare är aktiverad men låset saknas, är ofullständigt, olåst eller inte matchar observerad stack
- inga Qualcomm-/GenieX-versioner har gissats eller hårdkodats som fysiskt verifierade
- selfdev-, RPC-, restart- och config-spärrarna är oförsvagade

Exakt återstartspunkt:
1. börja från denna checkpoint på `dev/ventuno-q-provider`
2. kontrollera att aktuell branch-head och GitHub Actions fortfarande är gröna
3. fortsätt endast med rent mjukvarumässiga steg som inte kräver påhittad fysisk VENTUNO-verifiering
4. behåll deployment-låset avstängt tills riktig VENTUNO Q finns och den faktiska stacken kan fångas och granskas
5. när VENTUNO Q finns: kör config-validering, `scripts/ventuno_version_lock.py capture`, granska den verkliga stacken, aktivera först därefter ett permanent versionslås och fortsätt med `scripts/ventuno_preflight.py` enligt avsnitt 21.2


### 21.9 Återupptaget arbete 2026-10-05 – strukturerad felspårning

Nästa rena mjukvarulucka efter checkpoint 21.8 var kravet i avsnitt 17 att verktygsfel ska loggas och kunna felsökas utan att assistenten låtsas att ett misslyckat verktyg fungerade.

Implementerat på separat feature-gren:
- `core/error_log.py` med roterande strukturerad JSONL-logg
- tool-körfel loggas med `tool_error`
- modulimportfel loggas med `module_load_error`
- felloggen sparar inte rå användartext eller prompt
- felmeddelanden normaliseras och längdbegränsas
- loggning är best-effort och får aldrig maskera originalfelet
- befintligt multi-tool-beteende bevaras: ett misslyckat verktyg stoppar inte andra verktygsresultat
- nya konfigurationsvärden `error_logging.enabled`, `error_logging.path` och `error_logging.max_message_chars`
- fail-closed konfigurationsvalidering för aktiv felloggning
- separat testtäckning för skrivning, truncering, avstängt läge, loggfel och tool-integration

Verifiering:
- feature-head före denna dokumentationscommit: `5d360429cab75f80dcfff307592abb0143e59d5a`
- GitHub Actions-run `37276890394` är **success**
- Python-kompilering och full pytest-svit passerade
- ingen fysisk VENTUNO-verifiering har gjorts eller påståtts av detta lager


### 21.10 Återupptaget arbete 2026-10-05 – read-only feldiagnostik

Nästa steg efter den strukturerade felloggningen var att göra informationen praktiskt åtkomlig utan manuell filhantering.

Implementerat:
- `core.error_log.read_recent_errors()` läser de senaste strukturerade felposterna från aktuell och roterad JSONL-logg
- läsningen är hårt begränsad till högst 50 poster
- trasiga JSON-rader ignoreras och räknas separat
- `modules/system/errors.py` exponerar endast det read-only verktyget `myai_recent_errors`
- naturligt språk routar bland annat frågor som `Vilka fel har MyAI haft?` och `Visa MyAI fellogg.`
- `error_logging.recent_limit` styr standardantalet och valideras till intervallet 1–50
- verktyget ändrar, rensar eller kvitterar aldrig felloggen
- loggarnas integritetsregel kvarstår: rå användarfråga och prompt finns inte i de strukturerade felposterna

Verifiering:
- feature-head före denna dokumentationscommit: `f5529a435939684d48b4d2b8cefcf448563b27f5`
- GitHub Actions-run `37277666680` är **success**
- Python-kompilering och full pytest-svit passerade
- ingen fysisk VENTUNO-verifiering krävs eller påstås av detta read-only mjukvarulager


### 21.11 Återupptaget arbete 2026-10-05 – analys av VENTUNO-stabilitetstest

Första rekommenderade mjukvarusteget efter avsnitt 21.10 är nu implementerat: ett helt read-only analyslager för den senare 72-timmarskörningen.

Implementerat:
- `core.ventuno_stability.read_stability_records()` läser aktuell och roterad stabilitets-JSONL i kronologisk ordning utan att ändra filer
- läsningen är minnesbegränsad genom `stability_analysis.max_records` och har ett absolut tak på 100000 poster
- ogiltiga JSONL-rader räknas och ignoreras i stället för att krascha hela rapporten
- `analyze_stability_records()` sammanställer lyckade/misslyckade iterationer, lyckandegrad, längsta felserie och observerat tidsomfång
- latens rapporteras som p50, p95 och max för både first-token/first-chunk och total svarstid
- backendfördelning och antal backendbyten sammanställs
- CPU, RAM, disk och temperatur sammanställs från faktiskt loggade mätvärden utan att hitta på saknade värden
- relativa trendmått jämför median i början och slutet av loggen; standardflagga för latensförsämring är 1.25× och kan justeras i konfiguration
- `stability_analysis.target_hours=72` markerar endast om loggens observerade tidsomfång når målperioden; detta är inte ett hårdvarugodkännande
- `scripts/ventuno_stability_report.py` kan skriva svensk text eller maskinläsbar JSON från befintlig logg
- read-only verktyget `ventuno_stability_report` kan anropas med naturligt språk, exempelvis `Visa VENTUNO stabilitetsrapport`
- rapporten saknar alla restart-, skriv-, STM32-, GPIO- och NPU-styråtgärder
- rapportens `physical_hardware_approval` är uttryckligen `false`; fysisk acceptans ligger fortsatt separat i avsnitt 21.2
- configvalidering blockerar ogiltig loggsökväg, record-gräns, målperiod, trendfönster och degraderingskvot

Verifiering:
- feature-head före denna dokumentationscommit: `a28987d87789ff380fb35fbd207184c74cdd2c63`
- GitHub Actions-run `37279410066` är **success**
- Python-kompilering och full pytest-svit passerade
- tester täcker roterade loggar, truncering, trasiga loggrader, statistik, felserier, backendbyten, relativa trender, read-only-beteende, configgränser och språkroute
- ingen fysisk VENTUNO Q-/NPU-/ASR-/VLM-/STM32-verifiering har genomförts eller härletts från rapporten

Nästa rekommenderade rena mjukvaruspår är minneslivscykel och konflikthantering enligt avsnitt 15.2–15.3, fortsatt utan beroende av fysisk VENTUNO-hårdvara.


### 21.12 Återupptaget arbete 2026-10-05 – minneslivscykel och konflikthantering

Andra rekommenderade mjukvarusteget efter avsnitt 21.11 är nu implementerat och verifierat i CI.

Implementerat:
- befintlig `memories`-tabell migreras bakåtkompatibelt utan dataförlust
- aktiva och ersatta minnen skiljs åt utan fysisk radering
- `MemoryStore.supersede()` ersätter ett aktivt minne atomiskt och bevarar gammal post med pekare till den nya
- normal sökning returnerar endast aktiva minnen
- `get_history()` behåller insyn i hela livscykeln
- read-only `list_stale()` kan identifiera gamla aktiva minnen när en åldersgräns senare aktiveras
- `core/memory_lifecycle.py` gör deterministisk konfliktanalys utan extern modell eller nätverk
- exakta dubletter sparas inte igen
- möjliga motstridiga minnen utan tydlig ersättningssignal går till `review`
- explicit uppdatering kan endast auto-supersede när exakt en stark kandidat passerar den högre supersede-tröskeln
- tvetydig explicit uppdatering med flera starka kandidater gör ingen databasändring och kräver granskning
- `MyAICore` använder livscykellagret vid automatisk långtidslagring men faller bakåtkompatibelt tillbaka för äldre/förenklade MemoryStore-implementationer
- ingen automatisk radering, TTL-delete eller fysisk hårdvaruåtgärd har lagts till

Verifiering:
- feature-head före denna dokumentationscommit: `6b454a78361389101da6f3fd2ed31d4ceff04595`
- GitHub Actions-run `37280656675` är **success**
- Python-kompilering och full pytest-svit passerade
- tester täcker legacy-schema-migrering, datahistorik, atomisk supersession, normal sökning, explicit entydig uppdatering, tvetydig konflikt, möjlig konflikt, dublett, unrelated save, stale-listning, MyAICore-integration och configvalidering
- ingen fysisk VENTUNO-verifiering krävs eller påstås av detta lager

Nästa rekommenderade rena mjukvaruspår är en separat audit-logg för lyckade, nekade och säkerhetsrelevanta skrivande åtgärder enligt avsnitt 18.


### 21.13 Återupptaget arbete 2026-10-05 – fail-closed audit-logg

Tredje rekommenderade mjukvarusteget efter avsnitt 21.12 är nu implementerat och verifierat i CI.

Implementerat:
- nytt `core/audit_log.py` med strukturerade, roterande JSONL-poster
- `attempt` måste kunna loggas innan en skrivning när `audit_logging.require_for_writes=true`
- om obligatorisk audit är avstängd eller loggfilen inte kan skrivas blockeras själva skrivningen innan mutation
- lyckade, nekade och misslyckade utfall loggas separat
- auditmetadata begränsas och normaliseras
- rå användarprompt, textfilinnehåll, Excel-värden och selfdev approval-fråser loggas inte
- workspace-skrivning och Excel-skrivverktyg är inkopplade
- selfdev promotion och rollback är inkopplade utan att försvaga befintliga exakta godkännandefraser, Bubblewrap-spärrar eller source-drift-skydd
- `read_recent_audit()` läser auditloggen read-only över roterade filer
- `myai_audit_status` exponerar endast read-only visning av senaste händelser
- naturligt språk stödjer exempelvis `Visa auditloggen` och `Vilka ändringar har MyAI gjort?`
- configvalidering kräver konsistent auditkonfiguration och begränsar read-only-visningen till högst 50 poster

Verifiering:
- första feature-head `e6f1221ab3cfccfe2f95e3d8faae2cf1cfe84135` gav en testfailure eftersom ett nytt test använde en ogiltig Excel-instruktion och nådde parserfelet innan write-disable-spärren
- testet korrigerades utan ändring av auditbeteendet
- korrigerad feature-head före denna dokumentationscommit: `314710f75a967c4351907cd7f0c987afea3982c7`
- GitHub Actions-run `37284275511` är **success**
- Python-kompilering och full pytest-svit passerade
- tester täcker obligatorisk audit, lagringsfel, best-effort result logging, nekade försök, loggrotation, workspace, Excel, selfdev promotion/rollback, sekretessregler, read-only auditstatus, språkroute och configvalidering
- ingen fysisk VENTUNO/NPU/STM32-verifiering krävs eller påstås av auditlagret

Nästa rekommenderade rena mjukvaruspår är en samlad read-only MyAI-diagnostikrapport som kombinerar configvalidering, health, senaste fel, auditstatus, deployment-lock-status och runtime-/providerstatus utan att utföra restart eller fysisk styrning.


### 21.14 Återupptaget arbete 2026-10-05 – samlad read-only diagnostik

Fjärde rekommenderade mjukvarusteget efter avsnitt 21.13 är nu implementerat och verifierat i CI.

Implementerat:
- nytt `core/diagnostics.py` som sammanställer flera redan befintliga read-only statuskällor
- konfigurationsvalidering inkluderas utan att ändra settings
- primär LLM-provider/modell, fallback-konfiguration, visionstatus och VENTUNO-profilläge rapporteras från konfiguration
- färsk eller stale MyAI-health läses från befintliga snapshots
- headless runtime-heartbeat läses read-only och klassas som färsk/stale med konfigurerbar gräns
- senaste strukturerade felloggsposter och audit-händelser inkluderas via befintliga bounded readers
- deployment-lock kontrolleras endast strukturellt; ingen observerad VENTUNO-stack samlas och inget GenieX-kommando körs av rapporten
- rapporten sätter explicit `physical_preflight_executed=false` och `physical_hardware_approval=false`
- rapporten kan därför inte användas som ersättning för fysisk preflight enligt avsnitt 21.2
- `scripts/myai_diagnostics.py` ger text- eller JSON-utdata
- read-only verktyget `myai_diagnostic_report` kan anropas genom naturligt språk, exempelvis `Gör en MyAI diagnostik`
- ingen restart, inference, nätverksstyrning, STM32/GPIO-skrivning eller annan fysisk I/O ingår

Konfiguration:
- `diagnostics.runtime_stale_seconds=30`
- värdet valideras fail-closed till intervallet 1–3600 sekunder
- runtime heartbeat bedöms minst mot tre heartbeat-intervall så korta schedulerfördröjningar inte automatiskt ger stale-status

Verifiering:
- feature-head före denna dokumentationscommit: `ad7300875f50852748cc23ca5f14f291cd24ab40`
- GitHub Actions-run `37285117197` är **success**
- Python-kompilering och full pytest-svit passerade
- tester täcker lokal health/runtime-status, stale heartbeat, senaste fel/audit, saknat deployment-lock, strukturellt giltigt lock, read-only-egenskap, explicit frånvaro av fysisk preflight/godkännande, configvalidering och språkroute
- ingen fysisk VENTUNO/NPU/ASR/VLM/STM32-verifiering har genomförts eller härletts

Nästa rekommenderade rena mjukvaruspår är konfigurationshärdning: schema/version, okända nycklar, profiljämförelse och kontrollerad migrationslogik utan att aktivera fysisk hårdvara.

---

## 22. Övergripande vision

Slutmålet är en personlig AI-assistent som upplevs som ett sammanhängande system snarare än en samling separata program.

Användaren ska kunna prata naturligt med assistenten och exempelvis säga:

> Sök efter Bluetooth-enheter i närheten.

> Hur mycket ström drar datorn just nu?

> Vad blir det för väder idag?

> Skapa ett Excel-dokument med de här uppgifterna.

> Kontrollera vilken GPIO jag ska använda till den här sensorn.

> Lägg till den här funktionen i din kod, testa den först och berätta om den fungerar.

AI:n ska själv kunna avgöra vilka verktyg som behövs, använda dem, kontrollera resultaten och svara tydligt.

Den ska vara lokal i grunden, utbyggbar, försiktig med osäker information och kapabel att växa tillsammans med hårdvaran och användarens framtida behov.

---

## 23. Levande specifikation

Detta dokument är inte slutgiltigt.

När nya idéer, funktioner eller krav tillkommer ska denna specifikation uppdateras.

Den ska fungera som projektets centrala målbild och användas för att avgöra:
- vad som ska byggas
- i vilken ordning
- vilka säkerhetskrav som gäller
- hur en funktion ska testas
- om en kodändring för projektet närmare slutmålet
