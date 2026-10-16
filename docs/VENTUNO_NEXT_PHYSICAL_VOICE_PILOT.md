# VENTUNO Q – första kontrollerade uppföljningen av det fysiska rösttestet

**Status:** Källkodsstaging, DRAFT, 2026-10-16. Ingen ny inspelning eller
uppspelning har auktoriserats av denna PR. Detta är en plan för den **nästa**
fysiska omgången, inte påståendet att inget fysiskt test någonsin gjorts.

## Verifierad fysisk utgångspunkt

Ett verkligt VENTUNO Q-test gjordes **2026-10-12**, se
[första Ollama-försöket](checkpoints/2026-10-12-ventuno-usb-ollama-first-live-dialog.md)
och [GitHub Actions-körning #38272896093](https://github.com/Harrokk/Myai/actions/runs/38272896093).

- USB-mikrofonen spelade in ett enda verkligt tresekundersklipp med
  icke-tyst PCM efter en kort, svag ljudsignal från högtalaren.
- Whisper Tiny avvisade transkriptionen som en icke godkänd testfråga.
  **Ingen** Ollama-chatbegäran eller slutlig uppläsning gjordes.
- Äldre separat verifiering omfattade hörbar svensk TTS, fysisk USB-signal,
  riktig Whisper Tiny CPU-inferens på ett offentligt svenskord och riktig
  GenieX/HTP-anknytning. Dessa var separata moment, inte ett komplett
  sammanhängande privat samtal.
- Mismatch-orsaken är **inte känd**. Det kan vara timing, nivå, brus eller
  tolkning. Ingen rå användarinspelning sparades.
- Engångssamtycket från oktober är förbrukat. Den här PR:n, ett grönt CI
  eller ordet "fortsätt" beviljar inte automatiskt en ny inspelning.

## Prioriterad testkedja: stoppa på första NEJ

| Grind | Kontroll och godkänt resultat | Behörighet |
| --- | --- | --- |
| G0. Källversion | Exakt 40-hex Git HEAD, oförändrad säker VENTUNO-profil med fysisk röst och skrivåtgärder OFF | GitHub/source-only |
| G1. Read-only board | ARM64, båda tjänsterna aktiva, USB capture+playback på avsett par, minst 8 GiB MemAvailable och 3 GiB temporärt utrymme | Lokal read-only |
| G2. Processer/resurser | Ingen felaktig parallell modellinstans eller okontrollerad writer; tidigare verktygs- och procfs-spärrar granskas utan automatisk upplåsning | Lokal read-only + mänsklig granskning |
| G3. Nytt engångssamtycke | Personen vid mikrofonen godkänner **exakt en** kort inspelning och låg volym för den granskade committen | Ny uttrycklig auktorisering |
| G4. Svensk talinmatning | En enda kontrollerad fras; endast grov signalklass, godkänd/underkänd transkription och latenser rapporteras | Samtyckesstyrd hårdvara |
| G5. LLM-svar och TTS | Endast om G4 ger godkänd testfras; svaret kommer från tillåten loopback/backend och spelas svagt en gång | Samma engångstillstånd |
| G6. Städning/rollback | Testets tillfälliga processer, minne och staging rensas, produktionens tjänster och `voice.enabled` är orörda | Stoppa och verifiera |
| G7. Separat NPU/HTP | Ingen NPU-prestanda får räknas som verifierad utan ett eget underhålls-/profileringsfönster, säker återställning och giltigt operatörsspår | **Separat senare samtycke** |

## Första körbara kontrollen – helt utan ljud

Från **exakt granskad checkout** kan källkodskontrollen köras:

```sh
python3 -B -m scripts.ventuno_physical_pilot_gate \
  --expected-sha <EXACT_REVIEWED_40_HEX_COMMIT> \
  --source-root .
```

När lokal read-only inspektion är lämplig på VENTUNO och samma checkout
har verifierats kan `--board-readonly` läggas till. Läget använder
befintliga `ventuno_usb_voice_dialog_readiness.inspect()`, som inspekterar
/proc, /dev och `systemctl is-active`, men **inte** öppnar ljud,
installerar paket eller startar modeller.

Detta läge kontrollerar dessutom **separat** att den redan installerade
produktionsprofilen i `/home/arduino/MyAI/config/profiles/ventuno_q.json`
fortfarande har samtliga riskflaggor bokstavligen `false`. En säker
checkout räcker inte om den faktiskt installerade profilen är osäker.
Resultatet visar bara en fast kategorikod, till exempel
`blocked-usb-reenumerated-or-inaccessible` eller
`blocked-inactive-services`; inga råa ALSA-enhetsnamn eller loggar.

GitHub Actions-körningen skiljer på **diagnostik framgångsrikt genomförd**
och **hårdvaran redo**. Den kan vara grön som källkodstest även om den
redovisar `Board read-only NO-GO`. Vid NO-GO ska nästa ljudförsök
**inte** startas, och den rapporterade spärren måste undersökas i ett
separat, read-only steg.

Ett pass betyder bara **tillåtet att separat be om engångssamtycke**.
Kontrollen har med avsikt **inga inspelnings-, uppspelnings-, NPU-,
GenieX-start-, upplåsnings- eller produktionsinstallationsflaggor**.
Utdata innehåller bara fasta kategorier och booleska statusfält,
aldrig mikrofonljud, transkript, tokens, URL:er, enhetsnamn eller
filnamn från användaren.

## Om nästa verkliga test misslyckas

- Ingen okontrollerad upprepning. Ett nytt ljudförsök kräver nytt
  uttryckligt tillstånd.
- Om ljudnivån är låg, klipper eller kategorin är okänd: kontrollera
  inspelningsfönster och routing separat. Diagnostik får endast lämna
  grova, integritetsskyddade kategorier.
- Om transkriptionen avvisas: anropa **inte** LLM eller TTS. Kontrollera
  endast den sanerade felkategorin och granskad programlogik.
- Om LLM/TTS fallerar: kontrollera hur testprocessen stängdes och att
  produktions-GenieX/MyAI fortfarande är aktiva. Inget automatiskt
  systemd-restartförsök eller röstfunktion-ON är tillåtet.

## Återstående avgränsningar

Grön syntetisk CI visar testbar källkod men **inte** mikrofonkvalitet,
riktigt handsfree-samtal, uppmätta ände-till-ände-svarstider,
fysisk Stop/eko eller NPU-operatorprofil. DRAFT-stacken måste granskas
och en exakt testversion väljas före nästa aktiva ljudprov.
