# MyAI – fullständig source-only inventering av GitHub runner-exponering

**Datum 2026-10-19. Bas:** DRAFT PR #347 på `a13e3c617e35cddfbd6b1b7756efd868e9ed3f85`. **Status: källkodssignalering utan adminåtkomst – produktion NO-GO.**

## Pass 1 – verkligt riskområde

I den aktuella projektgrenen finns ett mycket stort antal GitHub Actions-workflows (179 `.yml` i en separat GitHub-tree-läsning innan denna PR). Flera äldre arbetsflöden innehåller historiska namn och instruktioner för självhostad VENTUNO-/`arduino`-runner. Om en automatisk `push`, `pull_request`, `workflow_run` eller annan händelse kombineras med åtkomst till den fysiska runnern kan ett kodtest få åtkomst till en verklig enhet och dess användarkonto utan att någon användare avsåg ett hårdvarutest. Detta går inte att utesluta genom att inspektera bara den nya PR:ens egna CI-filer.

GitHub-kopplingen som användes för revisionen tillät källkodsträd och workflow-jobb men gav **inte** åtkomst via de frågade administratörsendpunkterna för `/actions/runners`, `/actions/permissions` eller `/actions/workflows`. Dessa förfrågningar nekades av den begränsade resursåtkomsten och gav ingen aktuell grupp-, online- eller rättighetsstatus. Det vore fel att påstå att runnern är avregistrerad, att den inte kan nås eller att gamla grenar är säkra.

## Pass 2 – read-only inventering

`scripts/audit_workflow_runner_exposure.py` läser **alla vanliga lokala YAML-filer** i en explicit katalog. Scriptet använder en konservativ textgenomgång, ingen exekvering, inget nätverk, inga administrativa GitHub-anrop, ingen `git`-mutation, ingen filskrivning och ingen VENTUNO-dispatch.

För varje workflow rapporterar det:
- potentiella automatiska triggers: `push`, `pull_request`, `pull_request_target`, `workflow_run`, `schedule` etc.;
- vid push-trigger försöker skannern känna igen explicit angivna grenar under `on.push.branches` och skiljer dessa från globbar eller otydliga/obegränsade branchfilter. En äldre explicit testgren är **fortfarande en granskningspost**: den blir inte automatiskt säker enbart för att pushen kräver ett visst branch-namn;
- manuella triggers inklusive `workflow_dispatch` och `workflow_call`;
- uttryckliga `runs-on`-fält och eventuell `self-hosted`/`ventuno-q`-referens;
- potentiella uttrycksbaserade runner-val (som **kräver manuell granskning**, inte räknas som säkra);
- textbaserade indikationer på skrivande tokenbehörigheter;
- särskilt markerad kombination av automatiskt event + self-hosted runner.

Inventeringen får **inte** producera ett automatiskt produktions-PASS: den innehåller alltid `historical_branches_checked=false`, `runner_group_admin_settings_verified=false`, `physical_ventuno_touched=false` och `production_deployment_authorized=false`.

**Begränsning:** utan full YAML-parser/exekveringsanalys kan källkodstext över- och underflagga dynamiska `if`-, återanvändbara workflow- och matrisuttryck. Dynamiska runnerfält rapporteras som granskningsbehov. Frånvaron av en indikation är inte ett bevis för faktisk avsaknad av åtkomst. Tidigare frysta grenar, GitHub-admininställningar och externa Actions-reusable workflows måste granskas via behöriga administrativa kontroller.

`tests/test_audit_workflow_runner_exposure.py` kör bland annat syntetiska positiva och negativa fixtures för automatisk självhostad körning, rent hosted jobb, manuellt triggerfall, dynamiskt runner-val, kommentarer, skrivbehörighetsindikatorer och att skannern är skrivskyddad. Det verifierar också att reportens NO-GO-fält inte får vändas till produktionsgodkännande.

`.github/workflows/runner-exposure-readonly-inventory.yml` kör bara på GitHub-hostad Ubuntu, läsbehörighet för token, exakt `GITHUB_SHA` och en temporär checkout. Rapporten skrivs enbart till den tillfälliga hostade jobbmiljön, inte till VENTUNO; CI-loggen visar sammanfattning och högst 35 källkodsträffar. Ingen trigger för `workflow_dispatch`, ingen self-hosted jobbrunner eller `systemctl`.

## Prioriterad manuell produktionsgräns – kräver separat administrativ auktorisation

1. Verifiera GitHub Settings → Actions → Runners och Runner groups, åtkomst för repo och workflows, nuvarande live/offline-status samt möjligheten för äldre branch-referenser att dispatcha fysisk runner. Detta är **läskontroller som återstår**, inte genomförda administrationsändringar.
2. Innan VENTUNO-körningar kan tillåtas måste den fysiska Linux-installationen kontrolleras för runner-UID/sudo-grupper, `systemd`-gränser, verifierar-/updater-/vittnes-UID, katalogbehörigheter och åtkomst till I/O/NPU-enheter. Kräv en separat godkänd underhållsplan innan någon tjänst ändras.
3. Före säker kodpromotion krävs verklig betrodd provisionering för signerare och oberoende head; testkoderna #338–347 kan **inte** användas i produktion.
4. Hårdvarutester behöver täcka audio/mikrofon, USB/BT, NPU/QNN/HTP, strömavbrott, eMMC-återhämtning, rollback och befintliga enhetsspecifika beroenden med autentiserad testkörning och fysisk användarnärvaro/godkännande.

**DRAFT/NO-GO:** denna PR ger bättre täckning av aktuellt source-träd men ändrar inga befintliga arbetsflöden på äldre grenar och spärrar inte i sig runner-åtkomst. Fullständig GitHub-hostad ARM64-svit och separat, exakt SHA-inventering måste vara gröna. Ingen `main`-merge eller ändring av VENTUNO.
