# Riskbaserad talverifiering – säker staging (2026-11-03)

Status: **DRAFT / source-only / DEFAULT OFF**. Ingen ändring på VENTUNO,
ingen mikrofon, inga produktionsverktyg och ingen aktivering av taldrift.

Bas: `Harrokk/Myai` DRAFT PR #374, commit
`455e935e6590eae9f1db4586d8eb39ac94df8eb8`.
Denna gren är *inte* en ersättning för #374 och ska inte mergas ännu.

## Prioritering och nuläge

1. **Riskkatalog och sista verktygsspärren – förberedd:** 
   `core/voice_risk_policy.py` klassificerar enbart tillåtna, registrerade
   read-only-verktyg som låg risk. Reversibla/lokala åtgärder kräver
   explicit säkerhetsmetadata för medelrisk. Ändringar, installationer
   och destruktiva verktyg blir kritiska; okänt eller ofullständigt blir
   blockerat. `core/voice_plan_attestation.py` har en extra gränskontroll
   när ett framtida auktoriserat tiered-läge är inkopplat.
2. **Verifieringsmotor – fristående syntetiskt testbar:**
   `core/voice_verification.py` kräver 1/1 vid låg, 2/2 vid medel och
   2/3 vid kritisk nivå. Varje röst måste komma från en registrerad,
   unik modellfamilj. Oväntat olika icke-tomma kritiska transkript,
   inklusive ändrade mål, siffror eller nekande ord, blockerar även om
   två modeller annars håller med. En tredje *registrerad* modell kan
   avstå (tomt transkript) utan att försvaga kravet på två exakta röster.
3. **Full integration till talmotor och behörighet – INTE FÄRDIG:**
   `VoicePipeline` kör fortfarande sin gamla väg. Ingen ny funktion får
   aktiveras förrän komplett attestering/identitetskedja och
   bekräftelse- och återkallelseflöde har implementerats och testats.

## Viktiga spärrar

- `voice.risk_tiered_verification_enabled` är `false` som standard,
  och `config_validation` **avvisar även uttrycklig aktivering** för
  att förhindra att en halv integration körs i produktion.
- De syntetiska testerna körs endast på GitHub-hostad ARM64 via
  `.github/workflows/tests.yml`. Ingen VENTUNO-workflow krävs.
- Äldre behörighetsgräns och tillåtna read-only-verktyg är oförändrade
  när tiered-läget är av.
- En framtida `voice_tier_authorize` får ALDRIG vara ett LLM-svar.
  Den ska skapas av den betrodda orkestratorn efter verifierade,
  identitetsbundna STT-röster och kontrolleras vid varje verktygsanrop.
  HMAC måste fortsatt omfatta full plan, säkerhetsmetadata, effektiva
  argument, callback-identitet och återkallelsetillstånd.
- Modellens `family` och `revision` i `trusted_models` måste härledas
  från fabriks-/laddningskontrollerade, versionslåsta vikter. En modell
  får aldrig själv tilldela sig en godkänd identitet via ASR-utdata.
- Tre instanser av samma Whisper-modell är **inte** tre oberoende röster.
- Ljudigenkänning verifierar inte användaridentitet. Kritiska åtgärder
  kräver separat behörighet/godkännande; riskfylld fysisk styrning kan
  behöva förbli helt otillgänglig via röst.

## Måste vara klart innan aktivering

- Betrodd modellkatalog med modellhash/versionslås och skilda
  modellfamiljer (Parakeet / Canary / Whisper är kandidater, inga
  modellinstallationer har skett här).
- Integrera tiered-risk i `VoicePipeline`, slutlig verktygsplan och
  `allow_voice_dispatch`; beviset ska vara kortlivat, unikt per session,
  återkallat vid Stop och bundet till originalplan och argument.
- Separat uttryckligt godkännande för kritiska verktyg, aldrig baserat
  enbart på STT-majoritet. Testa plan-drift, timeout, processkrasch,
  manuell återställning och partial outcome.
- Staged konfigurationsvalidering och två oberoende säkerhetsgranskningar.
- Hosted-only svenska kvalitets-/latens-/RAM-mätningar innan fysisk
  operatorgodkänd VENTUNO-pilot. Ingen storleks- eller svarstidsgaranti.

Detta är avsiktligt en säker grundläggning, inte en driftsatt ersättning
för de befintliga röstkommandona.
