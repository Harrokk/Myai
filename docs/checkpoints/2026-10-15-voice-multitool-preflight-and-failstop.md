# MyAI checkpoint – tvåstegsverifiering för röststyrda flerkommandon

Datum: 2026-10-15. Separat DRAFT-gren `dev/ventuno-voice-multitool-atomic-preflight-20261015` ovanpå [PR #182](https://github.com/Harrokk/Myai/pull/182). Ej mergad, installerad eller driftsatt.

## Bekräftat utgångsläge

- [PR #182 VENTUNO ARM64 CI #38676431076](https://github.com/Harrokk/Myai/actions/runs/38676431076): **2 092 passed, 15 skipped**, statisk source/privacy-audit PASS, 0 blockerande fynd.
- Röstflödets hög-riskplan binds via HMAC till faktisk `MyAICore`-dispatch. `run_tools(execution_guard=...)` kontrollerar aktuell metadata och indataparametrar direkt före varje Python-tool-anrop. Textvägen har sin tidigare per-verktygsfunktionalitet.

## Verifierad kodrisk och ändring

`core/tool_manager.py::run_tools` arbetade fortfarande **sekventiellt** även i bevakat röstläge: tidigare steg hann utföras innan ett senare steg nekades. Vid ett verkligt verktygsundantag fortsatte de efterföljande stegen, vilket kunde tillåta ytterligare ändrande operationer på ett ofullständigt underlag. Resultatet från ett misslyckat *sista* röstverktyg kunde dessutom innehålla råa exceptiondetaljer utan blockmarkör, vilket öppnade för en missvisande LLM-framgångstext.

**Korrigeringen används endast när `execution_guard` är satt:**

1. Före **alla** tool-anrop granskas hela listan av steg (max 16) mot existerande registrerade callables, deras effektiva indata och skyddsregeln. Dubbletter, saknade/ogiltiga registry entries eller en oauktoriserad delplan stoppar **alla steg**. Inga föregående read-only-verktyg körs i detta fall.
2. När planen har fått GO utförs stegen i sin tidigare ordning, men regeln körs **på nytt** mot aktuell live-registry precis före varje enskilt anrop. Om ett tidigare steg muterar nästa verktygs metadata eller HMAC-bunden plan upptäcks detta vid nästa steg: återstående verktyg får `EXECUTION_BLOCKED_MESSAGE`, ingen ytterligare körning.
3. Vid exception i ett verktyg får det **felande steget** också den fasta blockeringstexten, utan privata felmeddelanden, och inga efterföljande delkommandon anropas. `MyAICore` känner igen blockstatusen och returnerar ett bestämt stoppmeddelande utan LLM, inklusive streaming.
4. Den ordinarie textbaserade `run_tools(..., execution_guard=None)` behåller sin tidigare bakåtkompatibla regel: flera verktyg körs och individuella felresultat rapporteras utan att stoppa återstående textsteg.

## Testning

- [GitHub-hosted x86 synthetic-only CI #38685515489](https://github.com/Harrokk/Myai/actions/runs/38685515489) **SUCCESS: 27/27 passed**: 12 nya syntetiska testfall och de 15 befintliga HMAC-dispatchtesterna. Täckning: senare nekat write blockerar även tidigare read före start, dubblett, saknad registry och input, >16 delsteg, ändrad säkerhetsmetadata mellan steg, exception mitt i och sist, inga privata feldata, oförändrad textväg, integrerad `MyAICore.respond_voice` med nekad respektive godkänd synthetic multi-plan, samt `respond_voice_stream` på delvis misslyckat test.
- Ordinarie source-only ARM64 CI för **exakt senaste PR-head** måste verifieras efter checkpoint. Inga faktiska modellanrop, fysisk ljudhårdvara eller muterande MyAI-verktyg används i testerna.

## Säkerhetsgräns

En preflight med alla steg godkända är **inte en databastransaktion**. Om steg 1 redan hann köras och steg 2 därefter misslyckas återställs **inte** steg 1. Därför garanteras att inga **efterföljande** delsteg körs efter fel, inte fullständig atomicitet/rollback. Verktyg som returnerar ett fel som en vanlig textsträng i stället för att kasta undantag kan inte generellt skiljas från ett giltigt strängresultat; sådana behöver senare en konsekvent strukturerad felmodell.

Behörighetskontroller inne i själva verktygen behövs fortsatt, liksom fysisk mikrofon-/STT-verifiering när USB-ljudkortet åter finns. Ingen faktisk ny CPU-/HTP/NPU-körning, Qualcomm Cloud/API, modelluppladdning, GenieX service restart, sudo/apt, firmware, ACL/udev/grupp, kamera/ljud, produktionsinstallation eller merge har utförts. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk GitHub secret purge/Support cache är separat releaseblockerare; QAIRT 2.46 live-stöd och HTP-v75 operatorplacering är fortsatt obekräftade.
