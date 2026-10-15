# MyAI checkpoint – högriskbekräftelse: ändrad verktygsplan ger NO-GO

Datum: 2026-10-15. DRAFT-gren `dev/ventuno-voice-confirmation-plan-drift-nogo-20261015`, utgår från [PR #180](https://github.com/Harrokk/Myai/pull/180). Inga merges, installationer eller verkliga ljud-/modellkörningar.

## Tidigare verifierat

- [PR #180 full isolerad ARM64 CI #38634600145](https://github.com/Harrokk/Myai/actions/runs/38634600145): **2064 passed, 15 skipped**, statisk källkod-/privacy-audit PASS, 0 blockerande fynd.
- Tidigare högrisk röstflöde kräver tre skilda STT-instansobjekt, minst två ordagrant överensstämmande rösttolkningar och separat bekräftelse, där en av tre får avbryta.
- HTP-v75 körs inte när GenieX är aktiv; live QAIRT 2.46-molkatalog och verklig NPU-operatorplacering är fortfarande obevisade.

## Granskningsfynd och åtgärd

I `core/voice_pipeline.py` kördes en ny `_classify_risk(pending["transcript"])` efter tre godkända bekräftelser. Den tidigare ändringskontrollen gick vidare om `current_risk["level"] == "high"` och listan av verktygsnamn var **oförändrad**. Det lämnade flera risker:

1. Om `preview_tool_plan()` kastade ett fel fick aktuell risk `tool_plan_error` men ofta **tom verktygslista**; en ursprungligt tom lista kunde då oavsiktligt ge samma värde och släppa igenom. Ingen osäker plan ska kunna räknas som säker.
2. En plan som bytte verktyg frågade bara efter ett nytt `bekräfta` utan att användaren hade gett själva kommandot och sett dess nya innebörd på nytt.
3. Även med samma verktygsnamn kunde **argument** och **säkerhetsmetadata** (`write` kontra `destructive`) ändras; den gamla kontrollen upptäckte inte detta.
4. Tidsgränsen för röstbekräftelse kontrollerades efter STT, men inte efter det potentiellt långsamma `preview_tool_plan()`.

**Nuvarande ändring:**
- Om en verktygsplansgranskning misslyckas eller ger ogiltigt format redan vid kommandot returneras `clarify` utan väntande bekräftelse eller verktygsanrop, oavsett röstkonfidens.
- Vid nytt fel, ofullständigt granskningsunderlag, ändrad verktygslista, ändrad riskklass/reason eller ändrad **privat attesterad** plan rensas pending och `confirmation_cancelled` returneras. MyAI ber då användaren ge **hela kommandot igen**, inte bara säga ja på nytt.
- Verktygsplanens strukturerade `steps` (inklusive argument) och aktuella per-verktyg-`safety`-metadata signeras med en **hemlig per-röstsession HMAC-SHA256-nyckel**. Högst 16 steg och 32 KiB canonical JSON tillåts; JSON som inte går att serialisera leder till NO-GO. Signaturen kan jämföras utan att exponera verktygsargument eller en gissningsbar osaltad SHA av talad privat data. Nytt process-/sessionsnyckelmaterial loggas aldrig.
- Efter plan-kontrollen görs en ny klockkontroll före assistentens anrop. Om tidsgränsen löpt ut annulleras pending. Befintligt 2-av-3-röstquorum, avbryt-/negationsveto och verktygseffektgranskning behålls.
- Vid oförändrad verifierbar plan fungerar den befintliga lyckade bekräftelsen fortfarande; ofarliga frågor utan planner fortsätter genom vanlig rutt.

## Avgränsade syntetiska regressionstester

Nya tester i `tests/test_voice_pipeline.py` kontrollerar: initialt plannerfel, fel under bekräftelse, verktygsbyte, ändrad säkerhetsklass även med samma verktygsnamn, ändrade parametrar för samma verktyg, bortfall av planeringsfunktion, ogiltig plannerrespons, deadline överkörd **inne i** plannerkontrollen, oförändrad plan som fortfarande kan bekräftas, samt ofarliga frågor utan planner. Dessutom valideras att verktygsargument inte skrivs i riskresultatet och att olika sessioner har skilda privata HMAC-signaturer.

Separat [syntetisk GitHub-hosted x86 workflow #38673974956](https://github.com/Harrokk/Myai/actions/runs/38673974956) **SUCCESS: 71 passed**, med fejkad STT, fejkad assistent och inget riktigt ljud/verktyg. Full isolerad ARM64 CI skall utvärderas på **exakt senaste commit**.

## Kvarvarande säkerhetsgränser

Denna fix gör jämförelsen mellan två **preview-resultat** striktare, men en preview är inte en transaktionslåst verktygsexekvering: riktig dispatch måste fortfarande själv ha säkerhetsspärrar, behörigheter och kan behöva en atomic plan-ID-check. Röstmajoritet är inte identitetskontroll. En profil med avstängd `high_risk_confirmation_enabled` får fortfarande andra säkerhetskrav; denna ändring gäller primärt den aktiverade bekräftelserutten.

Ingen mikrofon-/USB-ljudkortsåtkomst, lokal GenieX/Ollama-modellkörning, HTP/QNN-test, Qualcomm-token/molnuppladdning, tjänste-/firmware-/udev-/grupp-/ACL-/kameraändring, driftsättning eller merge. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk sekretessrensning/Support-cache kvarstår fristående releaseblockerare.
