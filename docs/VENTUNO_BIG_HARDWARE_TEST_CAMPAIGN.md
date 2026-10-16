# MyAI – slutlig fjärrförberedelse inför stora fysiska VENTUNO-tester

**Läge 2026-10-16:** Isolerade GitHub-testkörningar och skrivskyddade hårdvarumetadata. Den här DRAFT-grenen installerar ingenting, öppnar inte ljud, kör ingen ny NPU-inferens och ger inte något inspelnings- eller driftgodkännande.

## Vad är faktiskt klart?

- VENTUNO Q är nåbar via självhostad GitHub-runner och har tidigare klarat fullständig ARM64-källkodssvit.
- Verkligt USB-ljud återanslöts och kontrollerades skrivskyddat 2026-10-16 06:25 CEST: ALSA kort/enhet **1:0**, capture och playback som åtkomliga teckenenheter. **Ingen** mikrofoninspelning eller uppspelning verifierades vid den kontrollen.
- Riktiga ljudmoment utfördes delvis 2026-10-12. En tresekunders USB-inspelning innehöll signal men Whisper avvisade testfrasen innan LLM/TTS. Separata TTS/GenieX-tester är inte bevis på en komplett ljudkedja.
- Den källkodstestade röstkedjan har isolerade scenarier för STT, LLM, verktyg, TTS, Stop, timeout, avbruten skrivning, idempotensspärr, kvitto och återställning. CI-testernas antal mäter *programbeteende*, inte fysisk ljudkvalitet.
- Profilen på den aktiva installationen har kontrollerats och har röstskrivning/övriga riskfunktioner avstängda. Ingen DRAFT-PR är driftsatt.
- NPU/HTP har tidigare separata tester, men **V75-operatorplacering, per-operation-cykler, isolerad profilering och säker återställning med faktisk belastning är ännu inte godkända**.

## Fjärrgrind för all hårdvaru-testberedskap

`scripts/ventuno_big_test_readiness.py` kombinerar fem befintliga granskade metadata-only rapporter: USB/röst, V75 NPU-metadata, HTP profileringsfunktioner, GenieX/HTP samtidighet samt systemd-recovery-dryrun. Varje underlag granskas lokalt men bara ett fåtal sanerade booleska värden och fasta kategorier får lämna körningen. Saknad rapport, oväntad sidaeffekt eller ogiltigt format ger **NO-GO**, aldrig automatisk åtgärd.

```sh
# Källkodstest / valfri torr simulering; ger aldrig hårdvarutillstånd:
python3 -B -m scripts.ventuno_big_test_readiness

# Endast på godkänt ARM64-testexemplar i temporär exakt checkout:
python3 -B -m scripts.ventuno_big_test_readiness --board-metadata-only
```

Grinden är **inte** en körplanerare eller ett fysiskt testkommando. Den ger aldrig NPU-körtillstånd och kan endast indikera att maskinen *kan vara redo att fråga om separat ljudsamtycke*. Kör dessutom den tidigare exakta Git-SHA- och live-produktionsprofilspärren innan något fysiskt samtyckesmoment.

## Testmatris för fysisk närvaro och mätningar

| Fas | Kontroll och mätning | GODKÄNT kräver | Stoppa vid |
| --- | --- | --- | --- |
| A. Staging | Exakt signerad/granskad commit, ren checkout, temporär testkatalog, rollback-plan | Matchande SHA, profil/röst OFF, inga skrivverktyg, ledig RAM/disk | Okänd commit eller aktiv skrivfunktion |
| B. I/O | ALSA par 1:0, USB behörighet, separat headset mikrofon + hörlurar | Kortet synligt och åtkomligt efter anslutning | USB omnumrerat, saknas, eller ljudnod oåtkomlig |
| C. Engångsljud | En ny godkänd 3s mikrofoninspelning, topp/RMS, jämnhet | Icke-tyst inspelning i förväntat fönster, privat buffert rensad | Tystnad, klippning, fel enhet, oväntad integritetsrisk |
| D. STT | Svensk testfras, lokal modell, återstående minne, STT-tid | Förväntad fraskategori utan att spara rå transkription, bounded latency | Oklar/fel fras eller för låg minnesmarginal |
| E. LLM + TTS | Högst ett godkänt lokalt svar och svag TTS via ALSA | Säkert svar, en uppspelning, inga dubbla anrop | Fel STT, modell saknas, timeout, felaktigt svar |
| F. Avbrott | Stop under STT/LLM/TTS och statusverktyg | Inga oavsiktliga nya effekter, korrekt osäker status | Försenad respons leder till ny skrivning |
| G. Resursprofil | Monotona delstegstider, RAM peak, CPU-belastning, CPU-temp och strömförbrukning vid kontrollerat pass | Sanerade antal/kvantiler och före/efter-marginaler, ingen termisk strypning | OOM, övertemperatur, instabil USB/ström |
| H. NPU staging | QAIRT versioner, FastRPC åtkomst, DSP-bibliotek, modell-/formatkompatibilitet | Alla respektive metadata-only förutsättningar dokumenterade | Fel SDK/driver/verktygsstöd |
| I. NPU exklusiv körning | Separat signed tiny input, kontrollerad servicepaus, oberoende recovery | Operatör på plats, fungerande out-of-band återställning, loggat rollback-resultat | GenieX fortfarande aktiv, osäker DSP, inga kvitton |
| J. HTP profil | Dokumenterad operatorplacering, riktiga per-op-cykler och CPU/NPU-tider | Verktyg och vendor-kompatibel modell för samma runtime, verkliga trace-artefakter | Profilflaggor saknas eller NPU inte mätbar |
| K. Återställning | Live MyAI/GenieX/runner, stdout privacy och profilflaggor | Alla produktionsinställningar oförändrade, tjänster verifierade aktiva | Skrivspärr okänd, restartpolicy förändrad |
| L. Stabilitet | Timvisa/sammanhängande tester efter fysisk Go | Inga krascher, svarstider och temperatur enligt definierade trösklar | Minnesläcka, thermal throttling, instabilt återfall |

**Mätmetod:** Mät delsteg med monotona klockor; rapportera antal, lägsta/median/p95 och feltyper. Ingen latens får hittas på eller härledas från CI-tests körningstid. Temperatur måste komma från verkliga hårdvarusensorer; inga defaultvärden om sensor saknas. Audio mäts enbart efter separat aktivt godkännande. Innan belastning kan övervakning och återställning provas mot syntetiska processer.

## Öppna spärrar

1. Färsk, **uttrycklig** ljudinspelning/uppspelning inför ett enda övervakat fullständigt röstförsök. Tidigare samtycke är redan använt.
2. Fysisk närvaro för native process/ljud och termisk-/strömprofil, med möjlighet till omedelbar stopp och restart om något går fel.
3. Separat, vendor-kompatibel NPU/HTP-modell plus verifierat profilverktyg och operatörsgodkänd exklusiv test-/återställningsprocedur; enbart metadata eller tidigare GenieX-anrop visar inte op-placement.
4. Fortsatt manuell granskning av tidigare känsliga processanrop, särskilt produktions-STT-underprocessen; ingen automatisk kodmerge/install.

När de fjärrbaserade kontrollerna är gröna är den korrekta slutsatsen **fjärrstaging slutförd, fysiska grindar kvar**, inte “MyAI 100 % testad” eller “NPU redo”.