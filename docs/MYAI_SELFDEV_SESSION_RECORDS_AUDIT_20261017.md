# MyAI – granskning av sessions- och verifieringsfiler (2026-10-17)

**Bas:** PR #278, commit `791f145d4b2092eab4ac20f3baca3627628e71b4`. **Gren:** `dev/manual-audit-selfdev-session-records-20261017`. Source-only DRAFT, ingen ändring av driftad MyAI eller produktionens rollback.

## Två pass: logik och säkerhet

**Pass 1:** Läste `SelfDevWorkspace.create()/metadata()/write_text()`, verifierarens resultatskrivning, promotion `_verification()` och selfdev review. Tidigare skapades `session.json` och `verification.json` med `Path.write_text()`, och konsumenterna gjorde `path.exists()/Path.read_text()`. Invalidering skedde med `self.verification_path.unlink()`.

**Pass 2:** En sent utbytt filsymlänk kunde leda en metadata- eller verifieringsläsning utanför sessionen. `verification.json` kan innehålla `passed: true` och andra promotionsspärrar; även om signering, digests och approvals valideras i andra lager måste en läsning inte förlita sig på en ompekad pathname. Skrivning med `Path.write_text` var inte atomär och kunde exponera halvfärdig JSON efter avbrott. Dessa fynd motiverar no-follow, regelbundna filtyper och atomär publicering.

## Genomförd ändring

- Nya privata API:er i `SelfDevWorkspace`: `_session_directory_fd()`, `_read_session_record()`, `_write_session_record()`, `save_session_metadata()`, `save_verification()`, `read_verification()`, `invalidate_verification()`.
- Båda JSON-namnen läses från en redan öppnad session-dirfd via `O_NOFOLLOW | O_NONBLOCK`. `fstat` kräver vanliga filer med en hårdlänk och en storleksgräns på 4 MiB för att begränsa RAM. Läsningen konverterar endast JSON-objekt till record.
- Nya poster skrivs via exklusiva slumpade temporära filer med `0o600`, `fsync`, `os.replace(src_dir_fd=..., dst_dir_fd=...)` och katalog-`fsync`. Existerande symlänkar, specialfiler eller hårdlänkade målfiler avvisas; ersättning är atomär.
- Invalidering av tidigare verifiering använder nu `os.unlink("verification.json", dir_fd=session_fd)`, så ett sent ompekat sessionsalias inte styr borttagningen till en annan katalog.
- `SelfDevVerifier.verify()`, `SelfDevPromotionManager._verification()` och `build_selfdev_review()` använder de nya metoderna. Saknat resultat förblir nekande och oläsliga/ogiltiga resultat tolkas inte som godkända.
- Sex syntetiska tester täcker symlänkad metadata, symlänkad godkänd verifiering, förhindrad skrivning till extern symlänk, rename-fel + tempstädning, namnbyte mitt under invalidering och för stora sessionfiler.

## Fortsatt NO-GO

- Detta ger **inte autentisering** av JSON-innehåll mot en aktör som kan skriva legitima vanliga filer i sessionskatalogen. Fil-/katalogägare, UID-isolering, signaturer och giltighetsperioder måste fortfarande granskas för full promotionssäkerhet.
- Sessionens förälderkataloger och en redan öppnad inode är fortfarande betrodd OS-/driftsättningsgräns. En privilegierad lokal process eller bind mount ligger utanför denna patch.
- Promotion använder fortfarande flera egna path-baserade käll-/mål-/rollback- och journalrutiner. MyAI-produktion och automatisk självändring får **inte** aktiveras utifrån endast gröna syntetiska tester.
- Tidigare staging-/source-drift-gränser, fysiska mikrofon-, NPU- och QAIRT-tester, fullständig nativ beroende-/licensrevision, full manuell filgranskning och oberoende release-/rollbackkontroll återstår. Ingen merge till main eller installation på VENTUNO.

**Verifiering:** full ARM64 source-only CI på exakt sista SHA krävs för denna DRAFT. Kodens funktionalitet på Windows med denna Linux-skyddspolicy är inte attesterad.
