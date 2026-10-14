# MyAI checkpoint – QAIRT 2.46 AI Hub-katalog, evidens och spärr

Datum: 2026-10-14. Förberedande utvecklingsgren efter [PR #171](https://github.com/Harrokk/Myai/pull/171); endast DRAFT, utan deployment.

## Verifierade källor och tekniskt kontrakt

- [Qualcomm – Working with Frameworks](https://workbench.aihub.qualcomm.com/docs/hub/frameworks.html): `Client.get_frameworks()` ger aktuellt stödda QAIRT-versioner och `qai-hub list-frameworks` är CLI-alternativ. `default` och `latest` är **taggar**, inte bevis för ett visst versionsnummer. Ange önskad QAIRT som `major.minor`, exempelvis `2.46`.
- [Qualcomm – Framework class](https://workbench.aihub.qualcomm.com/docs/hub/generated/qai_hub.Framework.html) beskriver fälten `name`, `api_version`, `full_version` och `api_tags`. Ett publikt exempel med annan QAIRT-version visar samma schema. Detta verifierar *formatet*, inte en viss live-version.
- [Qualcomm API](https://workbench.aihub.qualcomm.com/docs/hub/api.html): `--qairt_version 2.46` är syntaktiskt korrekt, **om** 2.46 verkligen finns i tjänsten; trekomponentsversioner är ogiltiga för den flaggan. Versionens tillgänglighet kan bero på tjänstens katalog och modell.
- [Arduino VENTUNO Q](https://docs.arduino.cc/tutorials/ventuno-q/getting-started-qc-ai-hub/): molnmålet heter exakt `Arduino VENTUNO Q`, kör Ubuntu 24.04; `QCS8275 (Proxy)` är Android-proxy. Inga numeriska SoC-ID:n ska gissas.
- Offentliga [Arduino VENTUNO-jobb med QAIRT 2.45](https://aihub.qualcomm.com/jobs/jgllw4omg) och [QAIRT 2.50](https://aihub.qualcomm.com/jobs/jpyo00j05) visar annan NPU-användning på denna målenhet. **Inget av dem bevisar att exakt 2.46 finns i nuvarande live-katalog för vår graf.**

## Ändringar i detta steg

`scripts/ventuno_qai_hub_framework_catalog_readonly.py` kan enbart läsa en *redan lokalt tillhandahållen normaliserad JSON-snapshot* av de officiellt definierade Framework-fälten. Exakt format:

```json
{
  "frameworks": [
    {
      "name": "QAIRT",
      "api_version": "2.46",
      "full_version": "2.46.0",
      "api_tags": []
    }
  ]
}
```

Exemplet ovan är **syntetiskt testunderlag**, **inte** ett uppmätt get_frameworks-svar! Scriptet ger status `snapshot_lists_246_live_availability_unverified` vid matchning, aldrig en påstådd säker live-version eller ett godkännande att köra molnjobb. Om inget utdrag finns är status `no_go_catalog_snapshot_not_supplied`.

- Hård gräns 16 KiB, 64 Framework-poster, kända fält exakt, sanerade `api_version`/`full_version`, inga dubbla JSON-nycklar eller två QAIRT-2.46-poster, inget filsymlink, O_NOFOLLOW och fstat-identitetskontroll. Råa poster, filvägar, privata strängar eller token loggas aldrig. Inga nätverksanrop sker.
- `scripts/ventuno_qai_hub_offhost_target_policy.py` hade en **osäker sanningsetikett**: en enkel anroparboolesk `ai_hub_version_246_listed=True` kunde ge `qairt_246_in_live_service_catalog_verified=true` utan live-API. Det har nu rättats. Denna flagga är alltid **false** tills oberoende autentiserad validering införs; booleska påståenden om version eller behörighet kan inte ensamma upphäva spärren. Status `no_go_246_catalog_claim_not_live_attested` gäller för obekräftade påståenden.
- 12 isolerade parser- och fil-säkerhetstester samt en regressionskontroll mot falskt påstående i den gamla policyn. Pinned `pytest==8.3.5` installeras endast i en tillfällig GitHub-hosted x86-venv. Full MyAI-testsvit och source/privacy audit körs enligt befintlig ARM64-CI.
- **Ingen** riktig AI Hub-klient, token, SDK, modelluppladdning, jobb, HTP- eller CPU-inferens anropas. Inga tjänster, paket eller filer på den aktiva VENTUNO ändras.

## Vad som återstår, och varför NO-GO är korrekt

Ingen legitimerad och färsk Qualcomm `get_frameworks()`-katalog har hämtats eller verifierats för användaren. En lokal kopia kan vara redigerad eller inaktuell. Även ett äkta 2.46 Framework-objekt verifierar **inte automatiskt** exakt Compile-and-Link- eller HTP-operatorstöd på målenheten. Dessa frågor kräver separat kontrollerad åtkomst och godkännande, med källans ursprung, version och giltighet.

Även efter eventuellt positivt framkomstbevis får ingen modell skickas till molnet utan användarens uttryckliga godkännande. QAIRT-nedladdningar, HTP-körning, start/omstart, sudo, udev/grupper, ljud, kamera och merge/deploy är utanför tillåtet arbetsområde. Historisk GitHub Support purge [PR #110](https://github.com/Harrokk/Myai/pull/110) är fortfarande separat releaseblockerare.
