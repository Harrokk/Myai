# MyAI – promotion kräver sessionsbundet och komplett sandboxprotokoll (2026-10-17)

**Bas:** godkänd DRAFT PR #310, commit `b5c47eb3ced3dd51c8289c6d3f6c615f5bb4b9d9`. Enbart ändringar i GitHub och source-only ARM64 CI. Ingen installation, aktiv promotion, rollback eller merge till main.

## Pass 1: logisk granskning – verifieringens tillit

`SelfDevVerifier.verify()` producerar ett protokoll med session-ID, sandboxstatus, returkoder, en lista av lyckade/misslyckade valideringskommandon, ändrade/nya/raderade filer och workspace-manifestdigest. `SelfDevPromotionManager._verification()` kontrollerade tidigare endast `passed`, strängen `sandbox=bubblewrap` samt två isoleringsflaggor; `_preflight_promotion()` jämförde manifestdigest och aktuell source-drift. Ett syntaktiskt giltigt JSON-objekt med bara `passed=true` och dessa flaggor kunde därför accepteras även utan **några** dokumenterade testresultat, sessionsidentitet eller returvärden.

Detta är ett konsistens- och revisionsspårsfel. Det är **inte** bevis för att en angripare med samma UID inte kan tillverka en komplett falsk verifieringsfil. En verifieringsfil som skrivs under en användarägarkatalog utan oberoende autentisering ger inte kryptografisk eller privilegierad proveniens.

## Pass 2: kod och regressioner

- `_verification()` kräver nu att `session_id` är exakt den aktiva selfdev-sessionen, `passed is True`, att `returncode` har **exakt** typen `int` med värdet 0, att `error is None`, `deleted == []`, `source_drift == []`, `network_isolated is True` och `host_devices_exposed is False`.
- `changed` och `added` måste vara stränglistor med tillåtna, kanoniska relativa källkodssökvägar utan dubbletter eller överlappning.
- `checks` måste vara en lista med exakt de typberoende kommandon som `SelfDevVerifier.build_validation_commands()` producerar för samtliga ändrade/nya filer (Python-compile, JSON, TOML, shell) i sorterad ordning, följt av **exakt ett** `pytest`-resultat. Varje kontroll måste ha `passed is True`, `type(returncode) is int and returncode == 0`, `error is None` och förväntad fil/kontrolltyp.
- `_preflight_promotion()` jämför inte längre bara `workspace_manifest_digest`, utan kräver även att `changed`, `added` och `deleted` exakt matchar en ny läsning av faktiskt manifest. Avvikelser avvisas före skapning av rollback-journal eller mutation av aktiv kod.
- Befintliga promotion-unit-testfixtures sparar nu kompletta **syntetiska** protokoll via sessionsskrivaren. Nya tester omfattar flaggprotokoll utan bevis, annat sessions-ID, åtta felaktiga globala statusfält, sju varianter av felaktiga/missade/duplicerade kommandoresultat, felaktig ändringsklassning trots samma manifest och kompatibilitet med protokollet som verkliga `SelfDevVerifier.verify()` producerar med syntetisk command-runner.
- Normal strukturerad verifiering och promotionbehörighet bibehålls; ingen verklig osandboxad testkörning tillåts.

## Öppna releaseblockerare

1. **Oberoende verifieringsproveniens saknas fortfarande.** En lokalt skrivbehörig användarprocess kan förfalska alla JSON-fält, inklusive checks och session-ID. En säker lösning behöver signerad/verifierad attestering från betrodd separat verifieringsprincipal, eller ett strikt process-/UID-skyddat evidence-flöde som promotionsprocessen inte själv kan fabricera. Att signera med en nyckel som angriparen under samma UID kan läsa eller anropa vore inte ett tillräckligt skydd.
2. Verifierarens returncode bygger på resultathanterarens utfall; olika command-runners måste granskas vad gäller verklig sandboxkörning, timeout och skydd mot spoofing. Proveniensgrinden återstår.
3. Övriga filsystemskapanden, kompletterande kod-/beroende-/SBOM-/licensrevision, verklig strömavbrottsrecovery och fysisk VENTUNO NPU-/ljudtestning återstår. Samtliga PR:er är DRAFT och NO-GO för main/deploy.

**Verifieringskrav:** hela ARM64 source-only sviten måste passera på exakt sista commit. Ett godkänt syntetiskt test är inte ett produktionsgodkännande.
