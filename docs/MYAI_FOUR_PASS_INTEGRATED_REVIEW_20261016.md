# MyAI – samlad fyra-passgranskning, källkodsversion 2026-10-16

**Utgångspunkt:** `Harrokk/Myai` DRAFT #261, #262, #264 och #265.  
**Integrerad granskningsgren:** `dev/manual-audit-integrated-pass4-20261016`.  
**Säkerhetsbeslut:** **NO-GO för produktion och fysisk aktivering.** En godkänd testsvit innebär att de specificerade åtgärderna fungerar, inte att varje källkodsrad, alla indirekta skript eller alla installerade binärbibliotek är slutattesterade.

## Pass 1 – kodstruktur och logik

Föregående två automatiska fullträdspass täcker AST, imports/syntax, statiska integritetsrisker, konfiguration, tester och Actions; kompletterande manuell granskning koncentrerades till verkliga in- och utgångar för känsliga data. Namngivna granskade filer:

- `core/voice_stt_persistent.py`, `core/voice_stt_process_group.py`, `core/deployment_lock.py`, `core/runtime_service.py`, `core/orchestration.py`, `core/tool_manager.py`, `core/config.py`, `core/error_log.py`, `core/public_web_client.py`
- `core/selfdev_promote.py`, `core/selfdev_verify.py`, `core/selfdev_workspace.py`, `core/voice_write_journal.py`, `core/geniex_client.py`
- `modules/internet/fetch.py`, `modules/files/workspace.py`, `modules/files/excel.py`, `modules/camera/capture.py`, `modules/location/gps.py`, `modules/bluetooth/connector.py`, `modules/voice/providers.py`.
- Sju `requirements*.txt`-filer, 28-artifakters ARM64-hashlås, historiska GitHub Actions med fysiska effekter och deras tester.

**Ej utfört som bokstavligt arbete:** mänsklig rad-för-rad-kontroll av varenda en av projektets omkring 520 Pythonfiler och av alla historiska grenar. Denna rapport påstår inte detta.

## Pass 2 – säkerhet, integritet, processkontroll

Verifierade fynd och åtgärder i staplade DRAFT-PR:er:

1. **Historiska engångsgodkännanden:** 12 äldre användar-/microphone-/USB-/GenieX-/Ollama-/HTP-jobb kunde fortfarande startas med tidigare commit- och grenfilter. DRAFT #262 sätter dem i karantän och testsäkrar att dubbla `if`-nycklar, ytterligare board-jobb eller återaktiverade körningar blockeras. Tre mycket gamla ljudjobb har ersatts av ofarliga arkivdefinitioner på den nya grenen; ursprung finns kvar i Git-historiken.
2. **Rå undantagstext:** `core/error_log.py` kunde skriva privat `str(error)` i JSONL, och `read_recent_errors` lämna ut historisk rå feltext. `core/tool_manager.py` och direkta web-, fil-, Excel-, kamera- och GPS-verktyg kunde också visa råa native undantag. DRAFT #265 anonymiserar lagring, läsning, tredjeparts-loggcallbacks och 12 direkta felutgångar. Kända användarinput-fel får en säker fast text.
3. **Återstående risk:** `core/public_web_client.py` gör källbaserad DNS-validering följd av en separat HTTP-anslutning och efterkontroll av peer-IP. Utan en bindning mellan validerad adress och faktiskt ansluten socket kan TOCTOU/DNS-rebind eller miljöproxyintroducerad risk inte uteslutas av den statiska koden ensam. Offentliga webbverktyg måste ha ytterligare genomgång av requests-adaptrar, proxyinställningar och socketnivå före stark SSRF-attest.
4. **Felloggarnas äldre innehåll:** Detta PR maskerar det som läses, men tar **inte** bort tidigare rå JSONL-data från lagring. En separat säker datarensning kan behövas på installerad VENTUNO och kräver beslut om retention/backup.
5. **Övrigt:** Fysisk native STT/Stop-kapplöpning, transient WAV vid strömavbrott, databas/WAL, systemd processgrupper och NPU/QAIRT har inte avhjälpts eller attesterats fysiskt av dessa källkodstester.

## Pass 3 – beroende-, supply-chain- och licenskontroll

- De **sju direkta kravfilerna** och separata 28-hashade CPython 3.12/aarch64-rösthjulen har granskats statiskt. Projektets fullständiga Python/OS/native dependency-SBOM och säkrade produktionslås saknas ännu.
- Direkt `requirements.txt` innehåller korrigerat versionsgolv `requests>=2.33.0,<3` för `CVE-2026-25645` och `urllib3>=2.8.0,<3` för `GHSA-vxq7-64xx-v4gw` och `GHSA-gh4c-6fx4-qh6g`; statisk policygrind kräver detta.
- Oberoende kontroll i DRAFT #264 visade att tidigare minverifiering inte avvisade motsägelsefulla bounds såsom `requests>=2.33.0,<=2.32.0`. Ny fail-closed parser och syntetiska tester läggs till på den integrerade grenen.
- Publicerade advisory-versioner verifierades mot Requests och urllib3:s upstream advisories, men **ingen aktuell fullständig pip-audit av installerade transitiva hjul, license checker, native SBOM eller QAIRT-ABI** har utförts. Förhindrad installation är en avsiktlig säkerhetsgräns.

## Pass 4 – oberoende återgranskning

- Riktade tester för dubbla jobbnivåvillkor, 12 historiska hårdvarujobb, begärda dependency-bounds, manipulerade/falska requirements, error-redaction i disk/GUI/loggplugins och 12 tool-felutgångar.
- Separat exakt-commit källkodstest på VENTUNO Q ska klara tvåpassig source audit och gamla source-release-gates, plus alla riktade syntetiska tester.
- Hela projektets source-only ARM64-testsvit måste bli grön på **exakt samma slutliga integrerade SHA**.
- **Ingen merge/deploy/ljudinspelning/NPU/HTP/initiering av Ollama eller systemd-korrigering** får ske utifrån ett grönt källkodstest.

## Kvarstående releaseblockerare

1. Oberoende manuell granskning och attest med fil- och radidentifiering för återstående källkod, kompletterad med komplett extern Actions-/skriptkallsgraf.
2. Komplett signerad/pinnad produktionsberoendestack (direkt/transitiv/native/OS), licensöversikt, aktualiserad sårbarhetsdatabas, kontrollerad installations- och backout-plan.
3. Verklig VENTUNO-process och laddade inställningar, ordinarie röstvenv, fysisk USB mikrofon→STT→LLM→TTS/Stop, RAM/temperatur, SQLite WAL-recovery och fysisk rollback.
4. NPU/HTP efter verifierat matchande QAIRT/driver/DLC, operatör närvarande, exklusiv testprofil och fungerande oberoende återställning.

**Beslut:** Vi har genomfört och testat en betydande fördjupad kod- och beroenderevision i fyra arbetspass med spårbara korrigeringar. Vi kan inte sanningsenligt kalla hela den bokstavliga manuella rad-för-rad- eller produktionsberoendegranskningen färdig utan de uttryckligen listade återstående arbetena.
