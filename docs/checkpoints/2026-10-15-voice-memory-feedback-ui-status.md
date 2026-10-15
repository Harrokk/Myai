# MyAI checkpoint – minnesstatus genom röst och gränssnitt

Datum: 2026-10-15. Source-only utvecklingsgren `dev/ventuno-voice-memory-feedback-status-20261015`, stacked på [PR #189](https://github.com/Harrokk/Myai/pull/189). Endast DRAFT; ingen merge eller driftsättning.

## Verifierad utgångspunkt

- [PR #189 ARM64 CI #38694032558](https://github.com/Harrokk/Myai/actions/runs/38694032558): **2177 passed, 15 skipped**, statisk source/privacy audit PASS, 0 blockerande fynd.
- PR #189 introducerade ett sanitiserat `memory_feedback.status` från `MyAICore`, såsom `saved`, `already_present`, `retry_required`, `not_saved`, `pending_review`, `not_saved_sensitive` och `unverified`. Uttryckliga minneskommandon buffras under strömning tills SQLite-resultatet är kontrollerat, så modellen inte kan tala en falsk tidig "Jag har sparat".

## Fynd och ändring

`VoicePipeline.process_utterance` och `_handle_pending_confirmation` kontrollerade bara `tool_dispatch_blocked` och returnerade annars alltid `status="completed"`, **även om** `MyAICore.memory_feedback` redan sa att minnet inte sparats, väntade på granskning eller hade osäker auditlogg. GUI-/röst-/runtimesessioner som läser toppnivåns status kunde då visa falsk framgång trots rätt talat meddelande.

- `core/voice_pipeline.py` exponerar nu ett **sanitiserat** toppnivåfält `memory_feedback: {"status": "..."}` när kärnan returnerar det. Inga råa minneskandidater, feltexter, databasvägar eller privat feedbacksträng skickas till denna nya UI-status.
- Endast `saved`, `already_present` och `not_requested` behåller röstresultatet `completed`; `retry_required`, `not_saved`, `pending_review`, `not_saved_sensitive` och `unverified` återges som befintlig, UI-kompatibel `status="clarify"` med det redan verifierade `assistant.answer` som hörbart/skrivet besked. Verktyg som blockerats förblir också `clarify`.
- Även högriskvägens separata bekräftelsesvar tillämpar kontrollen; en faktiskt avlagd röstbekräftelse räknas inte som genomförd minneslagring. För ett hög-riskverktyg som blockerats är `confirmation.confirmed=False` fortsatt fallet; om bara minnesstatus kräver förtydligande kan röstbekräftelsen redovisas som mottagen men `status` inte som slutfört.
- Okänd eller felaktig (även icke-hashbar) feedbackstatus tolkas konservativt `unverified` i stället för att krascha eller godkänna åtgärden. Assistentimplementationer utan `memory_feedback` är fortsatt bakåtkompatibla.

## Syntetisk verifiering

- [GitHub-hosted x86 fake-STT/TTS/SQLite #38696910323](https://github.com/Harrokk/Myai/actions/runs/38696910323): **SUCCESS, 97 passed**. Omfattar 15 nya parameteriserade voice-to-UI-status- och riktiga `MyAICore`+ `VoicePipeline`-integrationsfall tillsammans med befintliga `test_voice_pipeline.py` och `test_memory_explicit_retry_feedback.py`. Verifierar success/retry/pending/secret/unverified/invalid status, gammal assistent utan fältet, TTS-stream, offline SQLite, återhämtning och att identiskt minne inte dubbelregistreras.
- Första isolerade testkörningen hade 95 pass och ett test som föll på en ofullständig testdubbel (saknade standardmetoden `respond_stream` för VoicePipeline:s stream-detektering). Enbart testdubbeln rättades. Senare 96 pass; den extra malformed-statusregressionen ger slutligen **97 pass**.
- Full isolerad ARM64 CI på **exakt sista PR-head** ska kontrolleras före slutligt grönt besked.

## Avgränsningar och följande prioritet

Detta skärper statusgränsen, men kontrollerar inte verklig svensk STT-noggrannhet, TTS-kvalitet eller fysisk USB-ljudåtkomst. Ingen verklig VENTUNO-databas, kamera, NPU/HTP/QNN, GenieX-process eller aktiv kod ändrades. Inga paket, firmware, grupp-/ACL-/udev-åtgärder, tjänsteomstarter, PR-merges eller produktionsuppdateringar. QAIRT-v75/HTP och historisk secret purge [PR #110](https://github.com/Harrokk/Myai/pull/110) förblir separata releaseblockerare.

**Nästa prioritet:** fortsätt med säker praktisk dialog- och verktygsintegration utan hårdvarutest, och kontrollera särskilt att administrativa UI-statusar för minnesgranskning och andra verktyg inte blandar ihop `pending`, `completed` och `failed`.
