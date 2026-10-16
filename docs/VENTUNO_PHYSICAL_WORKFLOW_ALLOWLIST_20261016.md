# VENTUNO – allowlist inför fysisk testdag (2026-10-16)

**Endast för den separat granskade integrationskandidaten i DRAFT PR #241.** Ingen av dessa regler aktiverar mikrofon, ljudutgång eller NPU. `main` och installerade VENTUNO-tjänster har inte ändrats.

## Automatiska CI-jobb som får användas före fysisk närvaro

1. `.github/workflows/ventuno-remote-preflight-completion.yml`: källkodstester på hosted Linux, skrivskyddade ARM64-metadata samt temporärt hashlåst voice-venv/native-import. **Inga modeller, inspelningar, GPIO, tjänsteändringar, NPU eller återställningsåtgärder.**
2. Projektets etablerade ARM64 source-only-suite på exakt SHA; rätta fel i DRAFT utan att ändra installerad kod.

## Ingen permanent auktorisering för gamla workflows

Fullträdsskannern `scripts/ventuno_all_workflow_preflight.py` kontrollerar alla källans Actions-filer och rapporterar fasta kategorier. Den ursprungliga översikten identifierade **17 möjliga ljud/HTP/diagnostik-workflows**, varav 7 med manuell workflow_dispatch och två falska grenmatchningar. Efter kontroll av flerradiga `push.branches` är de två exemplen begränsade till den historiska grenen `dev/routing-boundary-followup` – inte den här kandidaten.

Följande kända historiska flöden får **inte** köras för att prova riktig hårdvara utan separat operatörsbeslut:

- `ventuno-diagnostics.yml`: trots etiketten diagnostik innehåller det faktiska **GenieX-inferensanrop** och belastningsprov. Det är inte ett rent read-only-test.
- `ventuno-tiny-qnn-htp-once.yml`, `ventuno-tiny-qnn-htp-adsp-retry-once.yml`, `ventuno-tiny-htp-basic-profile-contract.yml`: HTP/QNN och vendor-kontroll; märkta historiska engångssteg är inte nytt samtycke.
- `ventuno-usb-dialogue-controller-safety.yml` och historiska `ventuno-usb-*-consent-once.yml`: hanterar ljud-/samtalsvägar; inget nytt ljudtillstånd kan härledas från workflow-namn eller commitmeddelande.
- `qairt-245-host-conversion.yml`: använder isolerad **x86**-SDK-konvertering, inte en godkänd fysisk HTP-väg; håll åtskild från användarens VENTUNO-test.
- Ytterligare historiska mikrofon-, eSpeak-/TTS- och QNN-skript ligger fortfarande i repoarkivet och behandlas som **NO-GO** tills deras exakta grenar, kod, körvillkor och följdeffekter har granskats individuellt.

De fyra main-unika legacy-jobben för integration, regression och runner-status är redan ersatta av inerta arkiv i kandidaten. `scripts/ventuno_main_workflow_quarantine.py` nekar om något av dessa börjar köra kod igen.

## Fysisk kampanj som separat beslutsprocess

Verkliga mikrofon-/högtalar-, GenieX- och HTP-jobb kräver utöver dessa källsäkerhetsregler:
- exakt godkänd commit och färsk aktiv VENTUNO-preflight,
- fysisk operatör vid enheten och nytt uttryckligt engångssamtycke för inspelning,
- stopp och verifiering av externa hjälpprocesser,
- fungerande out-of-band service-/enhetsåterställning innan exklusiv NPU,
- max en granskad aktiv testsekvens åt gången, med mätningar och verifierat rollback.

**Begränsning:** Fullträdsskannern är konservativ text-/triggeranalys, inte en fullständig tolkning av all GitHub Actions YAML, expressions, `uses:` eller sekundära skript. Den returnerar NO-GO om oklara automatiska kandidatgrensvägar kan starta hårdvara; dessutom kvarstår separat manuell granskning av historiska dispatch-jobb.
