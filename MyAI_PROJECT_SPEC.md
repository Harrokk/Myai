# MyAI – Project Specification

## 1. Syfte

MyAI ska vara en lokal, personlig AI-assistent som i första hand körs lokalt på användarens egen hårdvara men som kan använda internet när det behövs.

Systemet ska vara modulärt, utbyggbart och kunna växa från nuvarande Windows-baserade utvecklingsmiljö till att i framtiden köras på en Raspberry Pi 5B med utökat RAM-minne.

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
- Raspberry Pi 5B
- utökat RAM-minne
- lokal AI-modell anpassad efter tillgänglig prestanda
- möjlighet att ansluta externa sensorer, terminaler och annan hårdvara

Arkitekturen ska byggas så att så mycket kod som möjligt kan återanvändas vid flytten från Windows till Raspberry Pi.

---

## 4. Röst och ljud

AI:n ska kunna användas som en röstassistent.

### 4.1 Modulär röstarkitektur

Röstfunktionen ska byggas som en separat modul runt AI-kärnan.

Grundflödet ska vara:

**Mikrofon → röstaktivitetsdetektering → tal-till-text → MyAI-kärna → Ollama/LLM → text-till-tal → hörlurar/högtalare**

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

På Raspberry Pi 5B ska systemet kunna använda en resurssnål strategi där extra tolkningar endast körs vid behov.

### 4.7 Säkerhet före gissning

För röstkommandon med potentiellt stora konsekvenser ska MyAI hellre:
1. göra en extra taligenkänning
2. jämföra resultaten
3. kontrollera kommandots innebörd
4. fråga om förtydligande eller bekräftelse när det fortfarande finns rimlig osäkerhet

än att utföra en handling baserad på en osäker transkription.

### 4.4 Lokal och framtidssäker röstbehandling

På den nuvarande Windows-datorn ska systemet kunna använda en kraftfull lokal lösning för taligenkänning och text-till-tal.

Vid framtida flytt till Raspberry Pi 5B ska röstmodulerna kunna bytas mot lättare alternativ utan att resten av MyAI behöver ändras.

Röstbehandling ska i första hand kunna fungera lokalt, men externa tjänster ska kunna användas som valbara verktyg om användaren tillåter det och det ger en tydlig fördel.


Önskade funktioner:
- ta emot talade kommandon
- svara med tal
- fungera med Bluetooth-anslutna in-ear-hörlurar
- låta användaren styra funktioner med naturligt språk
- kunna läsa upp listor, statusinformation och resultat

På sikt ska användaren kunna använda AI:n utan att behöva titta på en skärm.

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

På utvecklingsgren finns nu en separat policy för automatiska terminalanslutningar. Policyn gör ingen faktisk Bluetooth-anslutning ännu, utan avgör endast om en observerad enhet får anslutas, ska behålla anslutningen eller bör kopplas från.

Policyn kräver att terminalen uttryckligen finns i konfigurationen, är markerad som betrodd och har automatisk anslutning aktiverad. Den använder separata RSSI-trösklar för anslutning och frånkoppling för att skapa hysteres och undvika att en terminal kopplar upp och ner vid små signalvariationer.

Standardläget är säkert: automatiska terminalanslutningar är avstängda och listan över betrodda terminaler är tom. Trösklar och per-terminal-regler kan justeras via konfiguration utan ändringar i kärnkoden.

Fysisk anslutning, faktisk terminalidentifiering och praktisk kalibrering av RSSI-trösklar ska verifieras senare i den samlade hårdvarurundan.

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

### 10.1 Teknisk status för Excel

På utvecklingsgren finns nu parameteriserade Excel-verktyg:
- `excel_create` för att skapa en arbetsbok
- `excel_read` för att läsa ett begränsat antal rader
- `excel_write_cell` för att skriva en specificerad cell
- `excel_append_row` för att lägga till en rad

Excel-filer hanteras initialt i den lokala, versionsignorerade mappen `runtime/documents/`. Absoluta sökvägar, enhetsbeteckningar och sökvägstraversering utanför den mappen blockeras.

Befintliga filer skrivs inte över vid skapande utan att `overwrite=true` uttryckligen anges.

Cellvärden begränsas till enkla Excel-värden. Strängar som börjar med `=` blockeras som standard för att undvika oavsiktliga formler. En formel får endast skrivas om `allow_formula=true` uttryckligen anges.

Excel-funktionerna använder det nya parameteriserade verktygssystemet och testas med riktiga `.xlsx`-filer i CI.

### 10.2 Teknisk status för lokala textdokument

På utvecklingsgren finns nu parameteriserade verktyg för lokala textdokument:
- `text_file_write` för att skapa eller uttryckligen skriva över en fil
- `text_file_read` för att läsa en fil med begränsad maximal svarslängd
- `text_file_append` för att lägga till text i en befintlig fil
- `document_list` för read-only listning av dokumentytan

Den första säkra filytan är `runtime/documents/`. Absoluta sökvägar, enhetsbeteckningar och traversal utanför dokumentytan blockeras.

Skrivbara filtyper är initialt begränsade till `.txt`, `.md`, `.json` och `.csv`. Kodfiler som `.py` skrivs inte genom detta dokumentverktyg; självkodning ska fortsatt gå genom den separata Git/sandbox-processen.

Skrivningar har en storleksgräns och läsning av långa filer avkortas till en konfigurerad verktygsgräns så att mycket stora dokument inte okontrollerat fyller modellkontexten.

Sökvägsskydd, overwrite-regler, append, listning och avkortning testas i CI.

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

### 12.1 Parameteriserade verktygsanrop

Verktygssystemet ska stödja både äldre verktyg utan argument och nya verktyg med strukturerade argument.

Ett verktyg kan deklarera ett enkelt JSON-schema i fältet `parameters`. MyAI:s verktygsplanerare ska då kunna skapa strukturerade anrop i formen:

`{"name": "verktyg", "arguments": {...}}`

Argument ska valideras innan funktionen körs. Obligatoriska argument, tillåtna fält, grundläggande datatyper och enum-värden ska kunna kontrolleras. Felaktiga argument ska ge ett tydligt verktygsfel och inte skickas blint till funktionen.

Direktroutade befintliga statusverktyg ska fortsätta fungera utan argument. Kompatibilitetsfunktionen `select_tools()` ska finnas kvar för äldre kod, medan AI-kärnan internt kan använda `select_tool_calls()`.

Detta lager är en förutsättning för framtida funktioner som exempelvis:
- filnamn och dokumentoperationer
- Excel-data och cellområden
- GPIO-nummer och elektriska parametrar
- kameraval
- webbsökfrågor
- produkt- och prisjämförelser

Parameterplanering, validering, bakåtkompatibilitet och exekvering testas automatiskt i CI.

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

### 13.0 Teknisk status för internetsökning

På utvecklingsgren finns nu verktyget `internet_search` med parameteriserad sökfråga och resultatgräns.

Första backend är ett generiskt SearXNG-kompatibelt JSON-gränssnitt. Detta gör att MyAI inte behöver låsas till en specifik kommersiell sökleverantör och möjliggör senare lokal eller självhostad sökinfrastruktur.

Internetsökning är avstängd som standard och kräver:
- `internet.enabled=true`
- provider `searxng`
- en uttryckligen konfigurerad `searxng_url`

Sökresultat normaliseras till titel, URL, kort utdrag, sökmotor och eventuell publiceringsinformation när dessa fält finns.

Klientformat, felvägar, resultatbegränsning och normalisering testas i CI. Verklig internetåtkomst och vald SearXNG-instans ska senare verifieras lokalt innan funktionen aktiveras som standard.

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

#### 13.1.1 Teknisk status för svensk totalprisjämförelse

På utvecklingsgren finns nu den parameteriserade jämförelsemotorn `price_compare_sweden`.

Varje erbjudande håller följande uppgifter separata:
- produktpris i SEK
- frakt i SEK
- momsstatus och eventuell separat moms
- andra tydligt angivna avgifter
- lagerstatus
- verifierad leverans till Sverige
- leveranstid när den finns
- säljarens interna tillförlitlighetsbedömning
- direktlänk och butik

MyAI ska inte anta att en kostnad är 0 bara för att den saknas. Om exempelvis frakt, moms eller avgifter inte är kända markeras totalpriset som ofullständigt och erbjudandet får inte rankas som fullt jämförbart.

Ett erbjudande räknas initialt som fullt jämförbart endast när:
- totalpriset går att beräkna
- leverans till Sverige är uttryckligen verifierad
- lagerstatus är `in_stock`
- säljarens tillförlitlighet når den konfigurerade miniminivån

Standardnivån för säljarens tillförlitlighet är 50 %. Högst tre erbjudanden presenteras i topplistan, sorterade efter faktiskt känt totalpris och därefter högre säljarbedömning.

Konfigurationen `shopping` innehåller standardgränser för toppresultat, minsta säljarbedömning och maximalt antal erbjudanden per jämförelse.

Detta lager är själva jämförelse- och räknemotorn. Automatisk extraktion av produktpris, frakt, moms, lager och leveransinformation från webbsidor byggs som ett separat nästa lager så att parsning och felrisk kan testas oberoende.

#### 13.1.2 Teknisk status för strukturerad produktutvinning

På utvecklingsgren finns nu verktyget `web_product_offer` för säker utvinning av strukturerad produktinformation från publika produktsidor.

Den säkra webbhämtaren fångar nu `application/ld+json` separat från vanlig sidtext. Vanliga scripts fortsätter att ignoreras.

Produktutvinningen letar i första hand efter schema.org-objekt av typerna `Product`, `Offer` och `AggregateOffer` och kan läsa:
- produktnamn
- produktpris
- valuta
- lagerstatus
- säljarnamn när det finns
- explicit VAT-inkluderingsflagga när sidan anger den
- explicit fraktkostnad i SEK när den anges i strukturerad data
- explicit leveransdestination Sverige när den anges

MyAI ska inte anta:
- att priset är i SEK om annan valuta anges
- att moms ingår om det inte uttryckligen framgår
- att frakt är gratis om fraktfält saknas
- att butiken levererar till Sverige om destination saknas
- att en sida utan JSON-LD saknar produkt eller erbjudande

Om strukturerad Product/Offer-data saknas ska verktyget därför rapportera att data saknas i stället för att gissa värden ur sidtexten.

Detta lager är avsett att ge högkvalitativa strukturerade indata till totalprisjämförelsemotorn. Valutakonvertering, säljarbedömning och sammanslagning av flera produktsidor byggs i separata lager.

#### 13.1.3 Teknisk status för valutakonvertering och säljargranskning

På utvecklingsgren finns nu verktyget `currency_to_sek` och en separat FX-klient.

SEK lämnas oförändrat utan nätverksanrop. Andra valutor konverteras endast när en faktisk kurs kan hämtas från den konfigurerade FX-leverantören. Första backend är Frankfurter-kompatibel och standardadressen är `https://api.frankfurter.app`. Om kurs inte kan hämtas ska priset förbli okonverterat och får inte gissas.

Produktutvinningen bevarar nu även fraktbelopp och fraktvaluta för icke-SEK-frakt så att samma faktiska kurs kan användas för både vara och frakt.

På samma utvecklingsgren finns också `seller_vetting`, som granskar säljsidan separat från produktpriset. Bedömningen kan väga in:
- HTTPS
- sidans transparenssignal
- kontakt-/kundserviceinformation
- retur-/återbetalningsinformation
- köpvillkor
- integritetsinformation
- organisations-/VAT-information
- etablerade betalningsalternativ
- tydliga varningssignaler som formuleringar om endast banköverföring eller krypto

Säljarpoängen är begränsad till högst 85 % och är en intern heuristisk risk-/transparensbedömning, inte en garanti för att säljaren eller köpet är säkert.

#### 13.1.4 Teknisk status för flerbutiks-shopping-research

På utvecklingsgren finns nu det parameteriserade verktyget `shopping_research_sweden`.

Standardflödet är:
1. ta en produktfråga och sök upp till fem kandidatsidor, eller använd uttryckligen angivna URL:er
2. hämta varje sida genom den säkra publika webbhämtaren
3. extrahera schema.org Product/Offer-data
4. verifiera sidans transparens och skapa en separat säljarbedömning
5. konvertera produktpris och frakt till SEK med faktisk FX-kurs när det krävs
6. mata de strukturerade erbjudandena till `price_compare_sweden`
7. presentera högst tre fullt jämförbara alternativ

Ett fel på en butikssida får inte stoppa resten av jämförelsen.

Shoppingflödet bevarar samma konservativa regler som tidigare lager: saknad valuta, frakt, moms, avgifter, lagerstatus, Sverige-leverans eller säljarbedömning gissas inte. Ett erbjudande med ofullständigt totalpris får därför inte hamna i topp tre bara för att listpriset ser lågt ut.

Detta innebär också att ett verkligt automatiskt shoppingresultat ibland kan innehålla noll fullt jämförbara alternativ. Då ska MyAI redovisa vilka uppgifter som saknas i stället för att fylla i dem med antaganden.

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

#### 13.2.1 Teknisk status för preliminär källbedömning

På utvecklingsgren finns nu en första deterministisk källbedömningsmotor.

Den håller tre värden separata:
- relevans mot användarens sökfråga
- källans preliminära tillförlitlighet
- informationens preliminära konfidens

Bedömningen på detta steg använder endast sökresultatens metadata och utdrag. Därför begränsas källtillförlitlighet till högst 80 % och informationskonfidens till högst 75 % innan själva källsidan har verifierats djupare.

Källtillförlitligheten kan bland annat väga in HTTPS, tydligt domännamn, publiceringsmetadata, informationsrikt utdrag, flera sökmotorsträffar samt varningssignaler som rå IP-adress, kortlänk eller punycode-domän.

Informationskonfidensen kan få ett begränsat stöd när liknande uppgifter återkommer på andra domäner. Resultat från samma domän räknas inte som oberoende bekräftelse.

Dessa procentsiffror är uttryckligen interna heuristiska bedömningar och inte matematiska sannolikheter för att ett påstående är sant.


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

#### 13.3.1 Teknisk status för fem kandidater → topp tre

På utvecklingsgren finns nu verktyget `research_top_three`.

Standardflödet är:
1. sök upp till fem kandidater via `internet_search`-lagret
2. beräkna relevans, preliminär källtillförlitlighet och preliminär informationskonfidens separat
3. kombinera värdena med konfigurerbara vikter
4. sortera kandidaterna
5. presentera högst tre resultat

Standardvikterna är:
- relevans: 40 %
- källtillförlitlighet: 35 %
- informationskonfidens: 25 %

Vikterna, kandidatgränsen och toppresultatgränsen ligger i konfiguration och kan senare finjusteras utan att kärnkoden ändras.

Om färre än fem kandidater finns ska det visas uttryckligen i resultatet.

Detta är första valideringsnivån. Djupare sidinhämtning, primärkälleidentifiering, författare/metod och faktisk motsägelseanalys ska byggas som senare lager innan procentsiffrorna får högre tak.

### 13.4 Säker publik webbsideshämtning

På utvecklingsgren finns nu verktyget `web_fetch_text` och en separat `PublicWebClient` som kan hämta text från en publik webbsida för djupare källverifiering.

Säkerhetsregler:
- endast `http` och `https` tillåts
- URL:er med inbäddade användaruppgifter blockeras
- värdnamnet DNS-upplöses före anslutning
- privata, loopback-, link-local-, reserverade och andra icke-publika IP-adresser blockeras
- varje redirect valideras på nytt innan den följs
- endast uttryckligen tillåtna textbaserade innehållstyper hämtas
- binära och okända innehållstyper blockeras
- maximal svarsstorlek begränsas i byte
- text som skickas vidare till modellen begränsas separat i antal tecken
- HTML reduceras till synlig text; script, style, noscript och SVG-innehåll tas inte med

Standardgränserna är 1 000 000 byte per sida, 20 000 texttecken och högst fem redirects. Gränserna ligger i konfigurationen och kan finjusteras senare.

Detta lager är grunden för djupare källgranskning. En lyckad sidinhämtning höjer inte automatiskt källtillförlitlighet eller informationskonfidens; innehållet måste först analyseras med tydliga verifieringsregler.

SSRF-skydd, redirect-kontroll, innehållstyper, storleksgränser och HTML-textutvinning testas i CI.

### 13.5 Djupare sidverifiering

På utvecklingsgren finns nu verktyget `web_verify_source` som använder den säkra publika webbhämtaren och bedömer verifieringssignaler på själva sidan.

HTML-hämtaren extraherar nu även:
- författarmetadata när sådan finns
- publiceringsdatum när sådan finns
- beskrivningsmetadata
- webbplats/utgivarnamn när det anges
- canonical-URL
- externa länkar

Sidverifieringen håller två nya mått separata:
1. **Transparensscore** – om sidan tydligt visar titel, författare, datum, beskrivning, canonical/utgivare, substantiell text och diskussion om begränsningar.
2. **Evidenssignalscore** – om sidtexten innehåller tydliga signaler om metod, data/resultat, referenser, DOI-liknande källor, externa länkar och begränsningar.

Transparensscore är begränsad till högst 90 % och evidenssignalscore till högst 85 %. Inte heller dessa mått är en sannolikhet för att sidans påståenden är sanna; de mäter endast synliga transparens- och evidenssignaler.

Verktyget kan även mäta enkel frågeöverlapp mellan användarens ämne och sidans text för att visa om den hämtade sidan faktiskt verkar handla om frågan.

Denna nivå är djupare än sökmetadata, men ännu inte full påståendefaktakontroll.

### 13.6 Djupverifierad topp-tre-rankning

På utvecklingsgren är djup sidverifiering nu kopplad till fem-kandidater-till-topp-tre-flödet.

Flödet är:
1. samla upp till fem kandidater
2. beräkna preliminär relevans, källtillförlitlighet och informationskonfidens
3. försöka hämta varje kandidats publika sida via den SSRF-skyddade webbhämtaren
4. beräkna transparens- och evidenssignalscore för de sidor som kan verifieras
5. blanda in sidpoängen i källtillförlitlighet och informationskonfidens
6. räkna om totalscoren
7. sortera om och presentera topp tre

Standardvärdet `research.deep_blend` är 0,40. Det betyder att 40 % av den justerade källtillförlitligheten kommer från sidans transparensscore och 40 % av den justerade informationskonfidensen kommer från sidans evidenssignalscore; resterande 60 % kommer från den preliminära sökbedömningen.

Efter djupverifiering kan:
- källtillförlitlighet som mest nå 90 %
- informationskonfidens som mest nå 85 %

En kandidat straffas inte automatiskt bara för att sidan inte gick att hämta. Om djupverifieringen misslyckas eller saknas behålls den preliminära bedömningen och statusen redovisas som misslyckad eller otillgänglig.

### 13.7 Konservativ motsägelseanalys

På utvecklingsgren finns nu en första konfliktmotor för tydliga numeriska motsägelser mellan oberoende domäner.

Första versionen flaggar endast konflikter när:
- två olika domäner beskriver liknande kontext
- båda anger ett numeriskt värde med samma stödda enhet
- skillnaden överskrider en konfigurerbar relativ tolerans

Standardtoleransen är 5 %. Exempel: två källor som beskriver samma effektmätning som 10 W respektive 6 W kan flaggas som konflikt.

Resultat från samma domän räknas inte som oberoende motsägelse.

När en konflikt hittas sänks informationens konfidens för de berörda kandidaterna med en konfigurerbar konfliktpåföljd, standard 10 poäng per konflikt och högst 30 poäng totalt. Rankingen räknas därefter om.

Konfliktmotorn är avsiktligt konservativ och täcker ännu inte fria språkliga motsägelser som “ökar” kontra “minskar” eller komplexa vetenskapliga slutsatser. Sådana semantiska konflikter ska byggas som ett separat senare lager för att undvika falska motsägelseflaggor.

Djupverifiering är aktiverad i projektets research-standardkonfiguration, men faktisk nätåtkomst är fortfarande blockerad tills `internet.enabled=true` och en sökbackend har konfigurerats.

Även de djupverifierade procentsiffrorna är interna heuristiska bedömningar, inte matematiska sannolikheter för att ett påstående är sant.

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

### 14.1 Teknisk status för lokal GPS-position

På utvecklingsgren finns nu ett separat verktyg `gps_status` för seriella NMEA-GPS-mottagare.

Lagret:
- är avstängt som standard
- kräver uttryckligen konfigurerad seriell port
- använder ett separat valbart `pyserial`-beroende
- verifierar NMEA-checksumman innan en rad accepteras
- stöder RMC- och GGA-meningar
- konverterar latitud/longitud till decimalgrader
- kan rapportera höjd, satellitantal, GPS-tid och hastighet när uppgifterna finns
- stänger serieporten efter varje läsförsök

Ogiltiga checksummor eller NMEA-rader utan giltig fix ska inte användas som position.

Parser, koordinatomvandling och felhantering testas i CI. Verklig GPS-port, mottagare och satellitfix ska verifieras senare i den samlade fysiska hårdvarurundan.

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

### 15.2 Minneshantering

På sikt ska det finnas tydliga regler för:
- vad som får sparas
- hur minnesvärde bedöms
- när korttidsminne flyttas till långtidsminne
- hur motstridiga uppgifter hanteras
- hur gamla uppgifter uppdateras
- hur länge information sparas
- hur den ändras
- hur den tas bort

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

### 16.1.4 Specialiserade visionuppgifter

På utvecklingsgren finns nu två specialiserade verktyg ovanpå samma visionklient:
- `vision_read_text` för OCR-liknande läsning av synlig text
- `vision_detect_objects` för en försiktig textbaserad lista över tydligt synliga objekt

Textläsningen instruerar modellen att återge endast text som faktiskt går att läsa och markera oläsliga delar i stället för att gissa.

Objektidentifieringen instruerar modellen att skilja mellan säkra och osäkra observationer och att inte hitta på fabrikat, identitet eller detaljer som inte kan avgöras visuellt.

Båda verktygen kan användas direkt på senaste bild eller i ett multi-tool-flöde där MyAI först tar en bild och därefter kör den specifika visionuppgiften.

Detta är semantiska visionuppgifter och inte geometrisk objektdetektering med bounding boxes. Om sådan exakt lokalisering behövs senare ska den byggas som ett separat lager.

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
- specialiserade visionverktyg för textläsning och försiktig objektidentifiering
- checksummeverifierad, standardavstängd seriell GPS/NMEA-positionering
- bakåtkompatibelt stöd för parameteriserade verktygsanrop med JSON-schema-validering
- säkra parameteriserade Excel-verktyg för skapa, läsa, skriva cell och lägga till rad
- säkra parameteriserade textfilverktyg för .txt, .md, .json och .csv i lokal dokumentyta
- standardavstängd parameteriserad internetsökning via konfigurerbar SearXNG-backend
- preliminär käll-/konfidensbedömning och konfigurerbart fem-kandidater-till-topp-tre-flöde
- säker publik webbsideshämtning med SSRF-, redirect-, innehållstyp- och storleksskydd
- djupare webbkällgranskning med sidmetadata, transparens- och evidenssignalpoäng
- konservativ numerisk motsägelseanalys mellan oberoende domäner med konfidenssänkning
- svensk totalprisjämförelsemotor med separata kostnader, lager, Sverige-leverans och säljartröskel
- säker schema.org/JSON-LD-produktutvinning för pris, valuta, lager, säljare och explicit Sverige-frakt
- faktisk FX-konvertering till SEK, separat säljargranskning och flerbutiks-shopping-research
- djupverifierad omrankning av fem kandidater till topp tre med konfigurerbar blandningsvikt och per-kandidat fallback

De fem ursprungliga systemverktygen ska fortsatt fungera:
- `gpu_status`
- `cpu_status`
- `ram_status`
- `temperature_status`
- `disk_status`

Därutöver finns:
- `usb_status`

Aktuell teknisk prioritet är att stabilisera den modulära kärnan och därefter fortsätta lägga till nya funktioner som separata moduler utan att bygga om terminalgränssnittet eller kärnan i onödan.

Innan utvecklingsgrenen mergas till `main` ska den även köras som ett lokalt smoke-test på Windows-datorn med riktig Ollama, NVIDIA-GPU och faktisk hårdvara, eftersom GitHub Actions inte kan verifiera all lokal hårdvaruåtkomst.

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
