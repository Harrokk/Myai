# MyAI – utökad manuell kod- och beroenderevision, pass 1–4

**Datum:** 2026-10-16  
**Granskad utgångspunkt:** [PR #261](https://github.com/Harrokk/Myai/pull/261), commit `90b3af1885ffd269809db04489acce58d76c4926`  
**Revisionsgren:** `dev/manual-audit-historical-device-gates-20261016`  
**Beslut:** Källkodskontroller och konkreta korrigeringar får godkännas först efter *exakt-SHA*-CI. **Full manuell rad-för-rad-granskning av hela projektet och alla transitiva beroenden är ännu inte slutattesterad.** Driftsättning och fysisk testning fortsatt **NO-GO**.

## Pass 1 – kod och logik

- Genomgång av hela Git-spårade trädet och två tidigare oberoende helträdsskanningar; kontroll av runtime, persistent STT, processgrupper, konfiguration, verktygsladdning, deployment lock och GitHub Actions.
- Manuell fördjupning på `core/voice_stt_persistent.py`: begärans nonce, deadline, gruppstädning, hantering av Stop, städningsfel och avvisning av föråldrat svar. Föregående skydd kvarstår. **Ingen riktig Whisper-process har körts i detta pass.**
- `core/deployment_lock.py`: versionslås är uttryckligt operatorstyrt; `resolve_project_path()` accepterar absoluta och relativa sökvägar. Därför ska oattesterad CLI-inmatning inte automatiskt få definiera fil som skrivs över. Denna risk kräver ett eget designbeslut om tillåtna destinationskataloger före produktionsinstallation.
- `core/tool_manager.py`: modulimport försöker fortsätta efter `Exception` och skriver rå exceptiontext i vissa äldre, oskyddade vägar. Potentiell P1-integritets- och felrapporteringsexponering behöver saneringsgräns innan oskyddat textflöde aktiveras. Skyddad röstdispatch redovisar redan mer konservativa utfall.
- Observerad manuell täckning: de namngivna högre riskfilerna och arbetsflödena i detta protokoll. Detta är **inte** ett påstående om full handgranskning av alla cirka 520 Pythonfiler eller alla kodrader. Kvarvarande filer måste fortfarande signeras av en separat läsgranskning för att rubriceras så.

## Pass 2 – säkerhet

En fördjupning i tolv gamla GitHub Actions-flöden visade att jobbnivån **fortfarande var körbar**, trots att tidigare grengränser och commitmeddelanden användes som engångssamtycke. Ursprungliga jobb omfattar fysiska mikrofon-/högtalarprov, faktisk lokal GenieX/HTP- eller Ollama-inferens samt installation av Ollama. De 12 fysiska jobben har fått jobbnivå `if: false` i **den nya DRAFT-grenen**, utan att ta bort kod, och ett separat syntetiskt verifieringsverktyg är tillagt.

| Historiskt jobb | Stängningsgrind |
| --- | --- |
| `ventuno-geniex-lazy-htp-once.yml` | Tidigare GenieX/HTP-körning avstängd |
| `ventuno-microphone-consent-once.yml` | Inspelning avstängd |
| `ventuno-microphone-plughw-once.yml` | Inspelning avstängd |
| `ventuno-ollama-installed-voice-reply-once.yml` | Modellinferens avstängd |
| `ventuno-ollama-user-install-once.yml` | Installation/modellprov avstängt |
| `ventuno-usb-dialog-consent-once.yml` | USB-dialog avstängd |
| `ventuno-usb-live-dialog-consent-once.yml` | USB-dialog avstängd |
| `ventuno-usb-microphone-consent-once.yml` | Inspelning avstängd |
| `ventuno-usb-microphone-corrected-once.yml` | Inspelning avstängd |
| `ventuno-usb-ollama-headphones-retry-once.yml` | USB/Ollama-dialog avstängd |
| `ventuno-usb-ollama-voice-consent-once.yml` | USB/Ollama-dialog avstängd |
| `ventuno-usb-speaker-consent-once.yml` | Uppspelning avstängd |

`scripts/ventuno_historical_consent_audit.py` kräver att den avstängda jobbnyckeln är **det första aktiva jobb-attributet**, att den förväntade self-hosted-jobbdefinitionen finns kvar och att inget extra self-hosted-jobb göms. Saknat/symlinkat/dubblerat innehåll underkänns. Detta skyddar endast den aktuella DRAFT-källan; gamla grenar kan fortfarande innehålla äldre historik.

**Ej slutattesterat:** fullständig manuell genomgång av varje YAML-expression, lokala indirekta skript, `uses:`-action-versioner, tredje parts nedladdade kod, exakta behov av `statuses:write`, processernas verkliga behörigheter och alla 824 ursprungliga filers kontrollflöden.

## Pass 3 – beroenden och publika säkerhetsbulletiner

Samtliga **sju direkta requirements-textfiler** har inventerats i källkoden:
`requirements.txt`, `requirements-voice.txt`, `requirements-ventuno.txt`, `requirements-bluetooth.txt`, `requirements-camera.txt`, `requirements-excel.txt`, `requirements-gps.txt`. Den åttonde filen `requirements-voice-arm64-hashed.lock` och tillhörande JSON innehåller en **separat 28-hjuls SHA-256-låsning för temporär röststaging på CPython 3.12/aarch64**. Den är inte hela produktionsstackens beroendelås.

**Konkreta sårbarhetsspår i HTTP-beroenden:**

1. `requests>=2.32,<3` tillät `requests<2.33.0`, vilka påverkas av den publicerade `CVE-2026-25645` (osäker återanvändning av temporär fil i ett ZIP-hjälpverktyg). **Åtgärd i DRAFT:** `requests>=2.33.0,<3`. Källa: https://advisories.gitlab.com/pypi/requests/CVE-2026-25645/
2. `urllib3` saknade explicit versionströskel och kunde därför, beroende på transitive resolution, ge en sårbar installation. Bland 2026-advisories: `GHSA-vxq7-64xx-v4gw` och `GHSA-gh4c-6fx4-qh6g`, korrigerade i **2.8.0**. **Åtgärd i DRAFT:** `urllib3>=2.8.0,<3`. Källa: https://github.com/advisories/GHSA-vxq7-64xx-v4gw och https://github.com/advisories/GHSA-gh4c-6fx4-qh6g

En statisk policygrind `scripts/ventuno_dependency_source_review.py` kräver minst dessa trösklar och en korrekt 28-artifaktsröstlåsning. **Detta är inte ett CVE-frihetsintyg.** Många andra beroenden är fortfarande versionsintervall eller o-hashade, och det finns inget exponerat komplett lås för hela produktionsmiljön. Faktiskt installerade versioner, native biblioteks-ABI, SPDX/licensvillkor och alla transitiva säkerhetsbulletiner har **inte** attesterats. Framtida installation måste först få en separat låst SBOM och offline-kontroll, utan att oövervakat ändra nuvarande `.venv`.

## Pass 4 – oberoende återgranskning

- Återkörning av tidigare tvåpassig helträds-AST/säkerhetsskanning samt finala, källkodsbaserade spärrar från PR #261.
- Separat syntetisk testsamling för de tolv historiska, frånkopplade fysiska jobben: reaktiverad `if:true`, endast step-level false, dubbla jobb, okända self-hosted-jobb, symlänkar, borttagna filer.
- Separat syntetisk testsamling för säkerhetsgolven i `requests`/`urllib3`, tidigare sårbara versioner, duplicerade paket, oönskade direkt-URL:er och manipulerade requirements-filer.
- Först när **full ARM64-projektsvit på exakt revisions-SHA** och denna separata grind har lyckats redovisas resultaten som verifierade. Godkänt test är inte manuell attest av all kod; rapportens återstående områden förblir uttryckligt öppna.

## Återstående grindar för en bokstavligen fullständig manuell revision

1. Fil-för-fil, funktion-för-funktion mänsklig granskning av hela den aktuella källkodsmängden med fil-/radintervall, signerat fyndregister och separat peer-review. Automatiska syntaxpass räcker inte som ersättning.
2. Komplett dependency-lock/SBOM för **hela** driftsmiljön, alla transitiva Pythonhjul, native `.so`, OS-paket, QAIRT/GenieX/LLVM, licens/ursprung och aktuell advisory-databas vid installationstidpunkten.
3. Fullständig genomgång av varje GitHub Actions `uses:`-beroende och anropade skript, inklusive aktuella behörigheter efter tänkt `main`-merge.
4. Verklig VENTUNO-runtime-verifiering: aktiva inställningar, installerad röststack, kontrollerad mikrofon–STT–LLM–TTS/Stop, testdatabas/WAL, process-reap och värden för CPU/RAM/temperatur.
5. Separat fysiskt HTP/NPU-test med verifierad återställningsförmåga och operatörssamtycke.

**Beslut:** Denna omgång har gjort konkreta kod-, säkerhets- och beroendekorrigeringar och förstärkt automatiska skydd. En bokstavligt **fullständig manuell** kod- och beroendegranskning kan ännu inte signeras. Ingen produktionsdrift eller fysisk aktivering är tillåten utifrån detta dokument.
