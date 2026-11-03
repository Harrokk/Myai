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

## Continued source-only integration (same DRAFT branch)

The following extra components have now been staged; none of this enables
production voice:

- `core/voice_tier_identity.py`: binds exact provider objects to distinct
  model families and pinned 64-character SHA256 weight identities supplied
  by a *trusted future model factory*, not by a model response.
- `core/voice_tier_authorization.py`: short-lived (at most 30 seconds),
  per-plan HMAC-bound, stop-revocable, single-use-per-tool authorization
  receipt; recomputes tool risk and rejects changed plans, callbacks,
  inputs, registry metadata, stale timestamps and replay.
- `core/voice_tier_flow.py`: staged synthetic route from primary STT,
  risk preview, optional independent backups, verification, receipt and
  per-invocation callback into existing `VoicePipeline._respond_and_speak`.
- `core/voice_pipeline.py`: switches to this route only when explicitly
  `risk_tiered_verification_enabled is True`; default legacy flow unchanged.
  A malformed flag is denied. The guarded callback now carries optional
  `voice_tier_authorize` so authorization is checked at actual dispatch.
- `tests/test_voice_tier_identity.py`,
  `tests/test_voice_tier_authorization.py` and
  `tests/test_voice_tier_flow.py`: synthetic identity, approval, risk
  escalation, plan drift, replay, stop, model disagreement and integration
  checks. No real models or hardware.

### Remaining security gates, deliberately NOT bypassed

1. Config validation **still rejects** enabling tiered mode, even if the
   runtime code now exposes a source-only path.
2. The production factory and VoiceSession do **not** supply
   `trusted_stt_bindings`. Thus there is no live trusted mapping from pinned
   model hashes to instantiated Parakeet/Canary/Whisper workers.
3. Actual three-model STT is not present on VENTUNO. The source-only
   integration tests substitute fake providers with intentionally synthetic
   bound identities; this is not a proof of real ASR provenance.
4. All **critical** commands remain unconditionally blocked by
   `TieredVoicePermit` even if 3 independent STT models agree. Physical
   consent/user identity must be separately designed, validated and
   implemented before any critical permissions are issued.
5. For medium risk, only allowlisted and explicitly reviewed reversible
   effects may be considered. Any tool whose metadata requires confirmation
   is escalated to critical regardless of effect label.
6. Real interruptions, performance and audio quality have not been tested
   on VENTUNO. The current STT deadline is observed after a provider call;
   native hard timeouts still need isolated worker support.

Do not remove the configuration hard-deny or merge this staging PR based only
on green unit tests. Production work needs a second security review,
hosted pinned-model tests and a separately approved physical-device pilot.
