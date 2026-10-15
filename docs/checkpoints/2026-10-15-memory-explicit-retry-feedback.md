# MyAI checkpoint – säker och tydlig återkoppling vid uppskjuten minneslagring

Datum: 2026-10-15. Separat source-only utvecklingsgren `dev/ventuno-memory-explicit-retry-feedback-20261015` ovanpå [PR #188](https://github.com/Harrokk/Myai/pull/188). Endast **DRAFT**: ingen sammanslagning, aktiv minnesdatabas, fysisk modell eller driftsättning.

## Verifierad baslinje

- [PR #188 full VENTUNO ARM64 CI #38692249714](https://github.com/Harrokk/Myai/actions/runs/38692249714): **2166 passed, 15 skipped**, statisk source/privacy-audit PASS, 0 blockerande fynd.
- [PR #188](https://github.com/Harrokk/Myai/pull/188) säkerställer idempotenta väntande minnesgranskningar via Unicode-/whitespace-normalisering, konfliktunion och atomisk `BEGIN IMMEDIATE`. Tidigare `MemoryStore.save_if_new` skyddar också mot exakta identiska aktiva minnen vid manuella återförsök; inga råa misslyckade minneskommandon köas av den nya ändringen.

## Konkreta problem

`MyAICore._finalize_response()` har sedan PR #186 haft korrekt intern `memory_decision.action="deferred_memory_unavailable"` / `saved=False` vid SQLite-läsfel. Men det tidigare synliga och talade `answer` kom från språkmodellen **innan** minneslagringen/-felet var verifierat. Därför kunde MyAI till exempel svara "Jag har sparat det" när ingen lagring hade utförts. Även ett fel i `save_if_new` eller en misslyckad revisionslogg efter *redan genomförd* skrivning kunde ge en oprecis eller farligt självsäker modelltext. Det behövdes även olika instruktioner för "inte sparat" respektive "sparat men audit ej bekräftad".

## Korrigering

- `core/memory_feedback.py` tillför ett separat, rent, sanitiserat statuskontrakt för **uttryckliga minneskommandon** (fraser i början av meddelandet såsom `Kom ihåg`, `Lägg på minnet`, `Spara detta`, `Spara att`, engelska `Remember this/that`). Fritextfrågor om hur minnet fungerar triggar inte felaktig retry-instruktion.
- `memory_feedback.status` anger `not_requested`, `saved`, `already_present`, `retry_required`, `not_saved`, `pending_review`, `not_saved_sensitive`, eller `unverified`, och innefattar bara fördefinierade svenska statusmeddelanden utan användarens råa minnestext eller undantagsdetaljer. För misslyckad uttrycklig lagring anges att **inget minne sparades** och att **hela instruktionen måste sägas på nytt** när långtidsminnet fungerar. Ingen automatisk återanvändning av tidigare dialogtext som skrivbegäran läggs till.
- Vid genomförd skrivning men misslyckad revisionsloggsbekräftelse ges status `unverified`: användaren uppmanas kontrollera minnet **före** omförsök, eftersom skrivningen faktiskt redan kan ha genomförts. Vid befintligt aktivt minne anges `already_present`; ingen ytterligare insättning krävs.
- För uttryckliga minneskommandon med enbart minnesfunktion ersätter `_finalize_response` ett spekulativt modellgenererat framgångssvar med det **deterministiska och korrekta** statusmeddelandet när sådant behövs. Kombinerade minnes-/verktygsfrågor bevarar övriga svar och får statusmeddelandet sist. Även det interna `memory_decision` förblir tillgängligt.
- `respond_stream()` buffrar tillfälligt **uttryckliga minnesinstruktioner** tills minnesbeslutet finns. Röst/TTS och streaming-callback får därmed aldrig ett tidigt "Sparat!" innan ett efterföljande SQLite-fel visar att lagringen inte lyckades. Vanliga frågor behåller sin vanliga streaming.
- **Integritet även under databasavbrott:** `contains_sensitive_memory_data` anropas för uttryckliga minneskommandon **före** "upprepa"-rekommendationen. Lösenord eller annan igenkänd känslig information blir `not_saved_sensitive`, aldrig ett krav att återge hemligheten igen. Inga privata sökvägar från `sqlite3` eller `audit_logger` ingår i svaret.

## Syntetisk regression och begränsningar

- [GitHub-hosted x86 synthetic memory-feedback #38693892797](https://github.com/Harrokk/Myai/actions/runs/38693892797): **SUCCESS: 52 passed**, inklusive nya autentiskt parser- och SQLite-faketestfall, befintliga minnesåterhämtnings- och assistenttester. Täckning: utebliven skrivning under outage, sanningsenlig ordinary/streaming-feedback, manuell explicit upprepning efter återställd DB med endast **ett** aktivt minne, inget automatiskt omspelande på "försök igen", explicit failed write, post-commit audit unverified utan andra insättningen, känsliga hemligheter under outage och oförändrat vanligt samtal.
- Ett äldre test för post-commit audit förväntade fortfarande LLM:s godtyckliga text trots reell loggosäkerhet; dess förväntan uppdaterades till den nya säkerhetsnotisen. Före denna sista CI var även riktade 50 tester gröna.
- Full source-only ARM64 CI på **exakt senaste PR-head** skall verifieras efter dokumentationscommit innan arbetet rapporteras som fullständigt verifierat.

**Begränsningar:** Detta ersätter inte auditlogg, är inte rollback/reparation av trasigt SQLite och garanterar inte att oförändrat identiska/semantiskt likvärdiga minnen aldrig dupliceras under alla stavningsvariationer. Det inför heller ingen lagringskö för privata råa misslyckade instruktioner; användaren ska ge hela kommandot igen när minnet fungerar. Streaming av uttryckliga minneskommandon kan svara något senare för att säkerställa korrekt status.

Ingen faktisk VENTUNO minnesdatabas, aktiv MyAI/GenieX-tjänst, USB-ljud, kamera, HTP/NPU/QNN, lokala modellvikter, Qualcomm-konto/moln, firmware, sudo/apt, ACL/udev/grupp, merge/deploy eller public Git-historik rördes. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk secret-history/Support-cache purge kvarstår separat releaseblockerare.
