# MyAI checkpoint – strukturerade verktygsresultat och ärlig delstatus för röstplaner

Datum: 2026-10-15. Separat DRAFT-gren `dev/ventuno-voice-structured-tool-outcomes-20261015` ovanpå [PR #183](https://github.com/Harrokk/Myai/pull/183). Ej mergad, installerad eller driftsatt.

## Baslinje

- [PR #183 fullständig isolerad ARM64 CI #38685618256](https://github.com/Harrokk/Myai/actions/runs/38685618256): **2104 passed, 15 skipped**, källkods- och integritetsgranskning PASS, 0 blockerande fynd.
- [PR #183 separat GitHub-hosted x86 syntetisk CI #38685515489](https://github.com/Harrokk/Myai/actions/runs/38685515489): **27/27** för komplett röstplans-preflight och fail-stop. Ingen fysisk inferens eller aktiv verktygskörning på VENTUNO.

## Konkreta problemet

Efter PR #183 kunde röstens `run_tools(execution_guard=...)` stoppa hela planen före start vid otillåtet steg, samt stoppa efterföljande steg om ett verktyg kastade exception. Men flera verktyg – särskilt `workspace_write`, `excel_create`, `excel_create_sheet`, `excel_append`, `excel_set_cell` och `memory_review_action` – fångar sina exceptions och returnerar vanliga strängar såsom `Kunde inte skriva filen:`. Körmotorn tolkade dessa strängar som **vanliga framgångsrika resultat** och kunde köra senare muterande delsteg. En röstrespons saknade också separat strukturerad information om vad som hann köras.

## Utförd korrigering

1. **Explicit kontrakt:** `core/tool_outcome.py` introducerar `ToolOutcome(success: bool, value: object)`. Ett nytt verktyg kan meddela misslyckande utan exception. Skrivskyddat skyddat röstflöde tolkar även den explicita strukturen `{"success": false}` som misslyckande, sanerar nyttolasten och stoppar efterföljande steg.
2. **Bakåtkompatibla adaptrar:** Befintliga skrivande fil-/Excel-/minnesverktyg får en explicit, avgränsad registry-lista med **kända felprefix** i `result_failure_prefixes`. Endast registrerade prefix tolkas som fail, inte text som råkar innehålla ordet `fel`. Alla äldre textresultat från den vanliga textvägen bevaras.
3. **HMAC-integritet:** Röstplanens privata signatur omfattar nu även dess effektiva `result_failure_prefixes` så att ett tidigare godkänt verktyg inte kan få sin felklassificering utbytt i senare steg utan att fail-stop-spärren slår till.
4. **Sanerade stegstatusar:** Endast när `execution_guard` finns fylls `outcome_details` med per-verktyg `state = succeeded|failed|blocked` och `attempted = true|false`. Ingen rå feltext, användarväg, argument eller privat uppgiftsdata inkluderas. Guard-avslag markerar `blocked, attempted=false`; exception och explicita fel efter ett anrop markeras `failed, attempted=true`. Efterföljande steg markeras `blocked, attempted=false`.
5. **Ärlig sammanfattning:** Röstens `MyAICore.respond_voice()` och strömmande motsvarighet ger `tool_execution_status = not_started|failed|partially_completed|completed`, eller `unknown` för felaktiga interna statusposter. `partially_completed` ges när minst ett steg rapporterades lyckat men en senare del inte fullföljdes. Ett entydigt **stoppmeddelande utan LLM** varnar då att tidigare ändringar kan ha utförts och att användaren bör kontrollera resultatet innan omförsök.
6. **Inget bakgrundstest på fysisk NPU/USB:** Allt testas med falska Pythonfunktioner och sanerade indata; ingen riktig workspace-/Excel-skrivning eller minnesradering utförs.

## Verifiering

- [Separata GitHub-hostade syntetiska tester #38687645926](https://github.com/Harrokk/Myai/actions/runs/38687645926): **44/44 PASS** efter att äldre tester justerats för skillnaden mellan misslyckat försökt steg och obehörigt/ej startat steg. De täcker både nya kontraktet, äldre failure-prefixadaptrar, registermutation, privat HMAC, ingen LLM vid blockering, delvis körda planer, vanliga textresultat samt regressioner från PR #182–183.
- Ett mellanliggande CI-fel gällde en saknad `EXECUTION_FAILED_MESSAGE`-import i ett befintligt test och att `respond_stream` fortfarande packade upp fem returvärden när `_prepare_response` nu returnerar sex. Båda har åtgärdats. En senare extra guard gör också att felbildade resultatuppgifter aldrig kan summeras som `completed`.
- Full isolerad VENTUNO ARM64 CI **på sista PR-SHA** skall verifieras separat; ange inte PASS förrän GitHub Actions markerar sista körningen som SUCCESS och rätt head SHA.

## Viktiga tekniska gränser

- Detta är en status- och **fail-stop**-mekanism, **inte rollback/transaktion**. Ett redan genomfört fil- eller minnessteg kan inte automatiskt ångras. Inte heller ett rapporterat `failed` betyder att verktyget med säkerhet inte hann göra någonting före felet.
- Endast explicit kontrakt, `{"success": false}`, samt **opt-in** registry-felprefix räknas säkert som fel. Äldre godtyckliga strängar från ett omärkt verktyg kan fortfarande inte tillförlitligt avgöras. Flytta återstående muterande verktyg till explicit kontrakt vid framtida arbete.
- Den textbaserade `run_tools(..., execution_guard=None)`-vägen behåller sina historiska resultat och fortsätter vid enskilda fel; denna PR stärker endast röstens säkerhet, inte generell permissions- eller användaridentitet.
- Verkliga USB-/svenska ASR-prov väntar tills ljudkortet åter är tillgängligt. HTP-v75 och autentiserad Qualcomm QAIRT 2.46-kompatibilitet är ännu inte bevisade.

Ingen modelluppladdning, extern Qualcomm API-access, fysisk HTP/NPU/CPU-inferens, omstart, ny tjänst, firmware-/paket-/udev-/grupp-/ACL-/kamera-/ljudändring, sammanslagning eller aktiv MyAI-driftsättning utfördes. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk secret purge/Support-cache förblir separat releaseblockerare.
