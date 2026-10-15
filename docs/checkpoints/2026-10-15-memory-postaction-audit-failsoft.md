# MyAI kontrollpunkt – fel i revisionslogg efter minnesåtgärd

Datum: 2026-10-15. Separat DRAFT-gren `dev/ventuno-memory-audit-postcommit-failsoft-20261015` ovanpå [PR #186](https://github.com/Harrokk/Myai/pull/186). Ej mergad, installerad eller driftsatt.

## Föregående verifierat läge

- [PR #186, full isolerad ARM64 CI #38689307096](https://github.com/Harrokk/Myai/actions/runs/38689307096): **2 152 passed, 15 skipped**, source/privacy-audit PASS med 0 blockerande.
- MyAI söker SQLite-minnen bokstavligt och fortsätter dialog med `memory_lookup_status=unavailable` vid tillfälliga läsfel, utan auto-save på den felande dialogturen.
- Skriv-, audit- och review-köfel returnerar redan fasta svenska statusmeddelanden utan privata sökvägar.

## Konkret fynd

`MyAICore._consider_long_term_memory` skrev först ett minne via `apply_memory_lifecycle` och anropade *sedan* `audit_logger.write_result(outcome=success)` utan skydd. Ett OSError eller SQLiteError i slutlig audit kunde då **krascha dialogen efter att minnet redan hade sparats**. Samma problem fanns i `_queue_memory_review` efter att granskningen redan lagts till. Även vägen för ett initialt misslyckat save/enqueue anropade `write_result` inne i sin exception-handler, vilket kunde maskera det verkliga originalfelet om även loggningen misslyckades.

## Kodändring

- En gemensam `_record_memory_audit_result(decision, **event)` omsluter nu alla fyra post-action-resultatloggningar för minneslagring och granskningskö (två success och två failure).
- Om slutlig audit lyckas ges `audit_result_status=recorded`, utan ändring av den redan registrerade faktiska minnes-/köstatusen.
- Om slutlig audit kastar exception ges `audit_result_status=unverified` och en **fast sanerad svensk `audit_result_error`**. Beslutets riktiga `saved`, `lifecycle_action`, `review_queued` och `review_id` behålls, även om loggningen misslyckas.
- **Ingen automatisk retry** av minneslagring eller enqueue. Detta undviker dubbelskrivningar efter oklara post-commit-loggfel. Nästa användarinstruktion kan bedömas separat.
- Ett senare lyckat audit-event på samma beslut får inte skriva över tidigare `unverified`; därmed syns även första loggningsbristen om t.ex. save och review båda sker under samma beslut.
- Feltexten, undantagsobjekt och interna sökvägar lämnas inte till dialogsvar. Detta är en ärlig **status om loggning**, inte bevis att diskens logg är oförändrad, konsistent eller möjlig att återskapa.

## Syntetiska tester

[Isolerad GitHub-hosted x86 CI #38691179913](https://github.com/Harrokk/Myai/actions/runs/38691179913): **SUCCESS, 47/47 passed**. Detta omfattar sex nya regressioner för:
1. redan genomförd minneslagring med misslyckad final audit – `saved=True`, en enda save, dialog och korttidshistorik kvar;
2. felande save och felande audit samtidigt – originalets `saved=False` samt sanerat `memory_error` bevaras;
3. skapad granskningspost och misslyckad audit – `review_id` och `review_queued=True` bevaras;
4. felande granskningskö samt felande audit – felstatus bevaras utan privata detaljer;
5. normal lyckad slutlig minnesaudit – `recorded`;
6. normal lyckad slutlig granskningsaudit – `recorded`.

Dessutom kördes sedan tidigare minnes-/assistenttester. Full isolerad ARM64 CI måste granskas på **exakt sista DRAFT-commit** innan PR anges som slutligt verifierad.

## Säkerhetsgränser

Statusen `saved=True` betyder att själva lagrings-API:t rapporterade framgång, inte en ny separat transaktionsverifiering. Misslyckad slutlogg kan betyda att audit-event skrevs delvis; `unverified` påstår därför inte att loggen säkert saknas. Det är inte en automatisk reparations-/replaymekanism och kringgår inte auditens tidigare **pre-write**-spärr: misslyckat `write_attempt` blockerar fortfarande lagringen.

Ingen aktiv VENTUNO SQLite/eMMC, GenieX, ljud, kamera, verktygsskrivning, QNN/NPU/HTP, Qualcomm AI Hub-konto, firmware, systemd, sudo/apt, udev/grupp/ACL, modelluppladdning, sammanslagning eller deployment ändrades. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk secret-history/Support-cache purge är fortfarande separat releaseblockerare.
