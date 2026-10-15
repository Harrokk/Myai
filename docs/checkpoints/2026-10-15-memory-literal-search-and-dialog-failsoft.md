# MyAI kontrollpunkt – bokstavlig minnessökning och felåterhämtning i dialogen

Datum: 2026-10-15. Separat DRAFT-gren `dev/ventuno-memory-literal-like-read-failsoft-20261015` ovanpå [PR #185](https://github.com/Harrokk/Myai/pull/185). Ej mergad, installerad eller driftsatt.

## Senast verifierat utgångsläge

- [PR #185 full isolerad ARM64 CI #38688513087](https://github.com/Harrokk/Myai/actions/runs/38688513087): **2138 passed, 15 skipped** och statisk source/privacy-audit PASS med 0 blockerande fynd.
- Projektets SQLite-minne har kort- och långtidsfunktioner, autominne, konflikthantering och en separat granskningskö. Inga verkliga minnesfiler från VENTUNO användes här.

## Konkreta fel och rättningar

### 1. Användartecken som SQL-wildcards

`MemoryStore.search` byggde tidigare mönster `%{keyword}%` utan SQL-`ESCAPE`. Det gjorde att en fråga om `100%`, en kod som `a_b` eller ett escape-tecken kunde ge breda och irrelevanta minnesträffar eftersom `%` och `_` har specialbetydelse i SQLite `LIKE`. Detta riskerar irrelevant/sensitivt långtidsminne i modellens systemprompt.

Nu behandlas sökorden som **bokstavlig text** genom att `!` escapes till `!!`, procent till `!%` och understreck till `!_`, varefter både poängsättning och sökvillkor använder `LIKE ? ESCAPE '!'`. Den normala sorteringen på överlappande ord, aktiva minnen och recency är oförändrad. Sökningarna är fortsatt parameteriserade.

### 2. Trasig minnesläsning avbröt dialogen

`MyAICore.build_system_message` anropade `memory.search` och `memory.format` utan recoverable-felhantering. Ett `sqlite3.Error` eller `OSError` kunde göra att ett vanligt svar eller ett streamat svar avbröts. Att felaktigt ersätta undantaget med "inga minnen" vore heller inte korrekt.

Vid dessa specifika läsfel sätts nu en internt kontrollerad **`memory_lookup_status="unavailable"`** och systemprompten får en neutral svensk text som säger att långtidsminnet inte kan läsas och inte får antas vara tomt. Dialogen kan fortsätta med tillgänglig information. Assistenten försöker **inte automatiskt spara ny minnesinformation under samma svar** och returnerar `memory_decision.action="deferred_memory_unavailable"`, `saved=False` till anropande UI. Nästa dialogtur försöker minnesläsning igen, så inget permanent avstängt minne introduceras. Inga råa SQLite-undantag eller databasvägar skickas vidare.

### 3. Privata detaljer från minnesfel

Befintliga vägar för `_consider_long_term_memory` och `_queue_memory_review` returnerade tidigare undantagens `str(error)` i `audit_error`, `memory_error`, `review_queue_error`. Fysiska databas-/auditlogg-sökvägar kan förekomma i sådana texter. Nu returneras enbart fasta svenska felmeddelanden för status vid audit-fel, minneslagringsfel och review-queue-fel; normal teknisk typklassning i auditloggen bevaras. Detta gör inte misstag till framgång.

## Syntetiskt testbevis

- [GitHub-hosted x86 #38689206530](https://github.com/Harrokk/Myai/actions/runs/38689206530) **SUCCESS: 41 passed**, bestående av de nya isolerade regressionerna och befintliga `tests/test_memory.py` samt `tests/test_assistant_core.py`.
- Tester använder **enbart syntetiska SQLite-filer i temporär testkatalog** och fake memory/LLM. De täcker bokstavliga `%`, `_`, `!` och sammansatta procent-/underscore-token, inget oavsiktligt återfinnande av fiktiva privata minnen, oförändrad normal flertokensökning, SQLite/OSError i läsning, vanlig och streamande dialog, oförändrad korttidshistorik, återhämtning nästa tur, ingen auto-save vid avbrott, och sanering av audit-, save- och review-fel.
- Separat full isolerad VENTUNO ARM64-source-only CI ska verifieras på **exakt slutlig commit**. Använd inte tidigare gröna körningar som slutlig evidens.

## Begränsningar

Detta är en **safe degraded mode** vid läsfel, inte reparation av en korrupt databas, migrering till ny lagring eller automatisk återställning av minnen. Om en användare uttryckligen säger "kom ihåg" vid avbrott står det `saved=False` och inga automatiska minnesändringar utförs; frågan måste upprepas när minnet är tillgängligt. `memory_lookup_status` är en intern status för MyAI, inte ett automatiskt verifierat hälsobesked om hela eMMC eller operativsystemet. Vid permanent databasfel krävs separat auktoriserad felsökning.

**Inte utfört:** ingen aktiv Ventuno-minnesdatabas öppnad eller ändrad; inga ändringar av GenieX/systemd, ljud/mikrofon, kamera, HTP/NPU/QNN, firmware, sudo/apt, ACL/udev/grupp, Qualcomm API, modelluppladdning, PR-merge eller produktion. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk GitHub-secret-purge och Support-cache förblir separat releaseblockerare. Live HTP-v75 och QAIRT 2.46-kompatibilitet kvarstår otestade.
