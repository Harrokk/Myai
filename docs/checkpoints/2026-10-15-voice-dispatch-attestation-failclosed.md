# MyAI checkpoint – bind röstsamtycke till verklig tool-dispatch

Datum: 2026-10-15. Separat DRAFT-gren `dev/ventuno-voice-dispatch-plan-binding-20261015` på [PR #181](https://github.com/Harrokk/Myai/pull/181), ej mergad och ej driftsatt.

## Bakgrund och konkret verifierad lucka

- [PR #181 full ARM64 CI #38674090310](https://github.com/Harrokk/Myai/actions/runs/38674090310) **2077 passed, 15 skipped**, källkod/privacy-audit PASS, 0 blockerande fynd.
- PR #181 såg till att taligenkänningens verktygsplans-preview aldrig får ändras efter första röstbekräftelsen utan att kommandot avbryts.
- Men `VoicePipeline._respond_and_speak` anropade fortfarande `assistant.respond(...)` eller `respond_stream(...)`, som i `MyAICore._prepare_response` gjorde en **ny** `select_tool_plan` och skickade verktygen direkt till `run_tools` utan att binda den nya exekveringsplanen till den godkända previewen. Därmed var röstsamtycke och faktisk tool-dispatch separata beslut. Detta var en **kodrisk**, inte belägg för tidigare skadlig eller oavsiktlig verktygskörning.

## Förändring på dispatchgränsen

- `core/voice_plan_attestation.py` är en gemensam isolerad HMAC-SHA256-hjälpare för VoicePipeline och MyAICore. Det som binds är högst 16 strukturerade plansteg inkl. indata, nuvarande verktygs-säkerhetsmetadata och identiteten hos funktionens aktiva callable-objekt. Max 32 KiB serialiserad JSON. Per-VoicePipeline 32-byte hemlig sessionsnyckel lämnar inte röstmodulen; oförändrade bytes kan jämföras med constant-time HMAC-kontroll. Ingen rå plan, HMAC-nyckel, användartext eller osaltad hash exponeras i verktygs-säkerhetsrapporten.
- `VoicePipeline` ger den godkända **internfunktionella verifieraren** till `MyAICore.respond_voice` / `respond_voice_stream` efter samma högriskbekräftelse som PR #180. Normala lågriskfrågor får ingen destruktiv auktorisation.
- `core/tool_manager.run_tools` har valfri `execution_guard`, anropad **precis före varje verktygsfunktion** med aktuell metadata och exakt effektiva indata. Vid avslag eller exception returneras en fixerad svensk blockeringstext, aldrig en exception med privata uppgifter, och verktygsfunktionen körs inte. Den vanliga *text*-rutten behåller sin befintliga kompatibilitet; säkerhetsgrinden är specifik för röstkörning.
- `MyAICore._prepare_response` använder denna kontroll för varje verktyg i röstläge. Utan giltig hög-risk-planverifiering kan bara ett **känt, uttryckligen allowlistat läsverktyg** köras, med oförändrad `read_only` metadata och korrekt indata. Farliga, saknade, lokala capture-, okända eller efterhandsmodifierade verktyg blockeras. Vid godkänd högriskplan måste hela aktuella planen, inklusive funktions- och effektmetadata, fortfarande HMAC-matcha vid dispatch.
- Äldre `BEKRÄFTA` för ett pågående flerstegs-webb-/mellanresultat kan **inte** ta röstvägen runt verktygsgaten. Dessa bekräftelser kräver tills vidare skriftligt separat godkännande.
- Om en röståtgärd blockeras returnerar MyAICore ett **deterministiskt** och tydligt stoppmeddelande utan att kalla språkmodellen, vare sig i vanlig eller strömmande svarsväg. VoicePipeline visar då `clarify` i stället för missvisande `completed`.
- Det muterande verktyget `memory_review_action` har dessutom fått explicit säkerhetsmetadata `effect="destructive"` och `voice_confirmation_required=True` i verktygsregistret. Det kan inte längre misstas för ett läsverktyg i röstens planering.

## Isolerad verifiering

- [GitHub-hostad x86-voice-dispatch #38676358112](https://github.com/Harrokk/Myai/actions/runs/38676358112): **15/15 syntetiska tester PASS**. Fake-minne, fake-LLM, fake-taligenkänning och anonyma Python-funktioner kontrollerar spärrad obekräftad skrivning, legitimt read-only, tidigare godkänd oförändrad plan, ändrat målargument/safety/callback, spärrad gammal intermediate-bekräftelse, stream-variant, felaktig plan och integrerat röstflöde utan faktisk effekt.
- Testmiljön behövde projektets standardberoenden `requests` och `psutil` utöver pinned `pytest`, därför installerades de **endast i GitHub-värddatorns temporära venv**. Första x86-insamlingen misslyckades på `ModuleNotFoundError: requests`; denna miljöbrist är åtgärdad. Ingen installation på VENTUNO.
- Ordinarie VENTUNO ARM64 CI (isolerad källkodsgranskning och testsvit) måste verifieras på slutlig commit; **inga** riktiga verktygs-skrivoperationer eller NPU-/LLM-modellkörningar ingår i vår ändring.

## Viktiga återstående gränser

Detta garanterar att MyAI:s **röstväg** inte skickar ett ändrat godkänt kommando till verktygsfunktionen, men verifierar inte identiteten hos den som talar, mikrofonens ljudmiljö eller att två STT-modeller är verkligt oberoende. Attesterade Python-callables och metadata förhindrar inte illvillig kod som redan kör med processens behörighet. Skriftliga, uttryckliga verktygsinstruktioner fortsätter genom ursprunglig textväg och befintliga per-verktygsgränser; nya dispatchgaten är inte ett generellt permissions-system. Kända läsverktyg kan fortfarande utföra externa read-only nätverksanrop när användaren uttryckligen frågar efter detta.

Historisk GitHub-secret-history/Support-cache purge i [PR #110](https://github.com/Harrokk/Myai/pull/110) är separat releaseblockerare. Ingen PR-merge, GenieX/Arduino-tjänsteomstart, audio, USB-mikrofon, kamera, HTP/NPU/QNN-modellkörning, firmware, grupp-/udev-/ACL-ändring, Qualcomm cloud-katalogfråga eller modelluppladdning utfördes. Verklig HTP-v75 och autentiserad QAIRT 2.46-molntillgänglighet kvarstår obevisade.
