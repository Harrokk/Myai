# MyAI – sessions-ID, projektrot och baslinjens integritet (2026-10-17)

**Bas:** verifierad DRAFT PR #313, exakt commit `a5de02f6447ebc22734a5a5fefac232baf0d3565`. Ändringen gäller enbart GitHub-källkod och source-only ARM64-tester. Ingen aktiv installation, självmodifiering eller merge.

## Pass 1 – faktisk dataflödesgranskning

`SelfDevWorkspace.create()` skriver `session.json` med `session_id`, `project_root`, `baseline` (tillåtna paths till SHA-256) och `baseline_digest` som SHA-256 över den kanoniserade baslinjekartan. `changed_files()` läser tidigare baslinje, jämför med stagingmanifest och lämnar deltalista. `source_drift()` läser samma metadata och kontrollerar aktiv källkod mot lagrade SHA-256-värden.

Efter PR #309–310 är JSON-läsningen säker mot observerbara samtidiga byten och tvetydiga JSON-nycklar. Dock användes de lagrade `session_id`, `project_root` och `baseline_digest` inte för en konsekvenskontroll innan `changed_files`/`source_drift` använder `baseline`. En sessionsfil kopierad från en annan session/projekt kunde alltså leda till felaktigt godkända baslinjevärden; en delvis ändrad baseline med kvarvarande digest avvisades inte. I värsta fall riskerar detta felaktiga ändrings-/driftbeslut före promotion.

## Pass 2 – kodändring och regressioner

- `SelfDevWorkspace.metadata()` läser fortfarande `session.json` via den redan granskade pinnade, stabila och strikta JSON-läsaren.
- Den kräver nu exakt `session_id == self.session_id` och `project_root == str(self.project_root)`.
- `baseline` måste vara ett objekt om högst 10 000 sökvägar. Varje nyckel valideras med befintlig `_manifest_parts` (allowlist, traversal och normaliserat POSIX-format) och varje värde måste vara ett 64-tecken hex SHA-256.
- `baseline_digest` måste vara 64-tecken hex och matcha `manifest_digest(baseline)`. Jämförelsen är konstanttidsimplementerad, men **sammandraget är inte nycklat** och ger inte äkthetsgaranti.
- Dessa kontroller gäller både `changed_files()` och `source_drift()`, vilka redan använder `metadata()`; före en inkonsistens uppstår stopp utan skrivning till aktiv kod.
- Fem nya regressionstestfunktioner (sex exekverade fall): metadata kopierad från annan session, annan projektrot, ändrad baseline utan digestuppdatering i båda funktionerna, felaktig digest, samt oförändrad giltig metadata.
- Ingen ändring av källkodspromotion, journalsignering, CLI-godkännande eller befintligt metadataformat.

## Öppna blockerande risker

- **Kryptografisk proveniens saknas fortfarande.** En process med samma användar-ID och skrivrätt till sessionskatalogen kan skapa en ny baseline och räkna om detta onycklade SHA-256-sammandrag. Ändringen kan inte ensam bevisa att sessionen skapats av MyAI:s betrodda verifierare. Kräver separat UID-/processseparation, autentiserad verifieringskedja och driftskontroll.
- Om äldre sessionsfiler saknar `baseline_digest` krävs en separat verifierad migration, inte tyst automatisk reparation; ogiltiga filer ska avvisas.
- Nya sessionskatalogalias kan flyttas av en icke-samarbetande privilegierad process, trots att alla verkliga läsningar nu går via no-follow-descriptorvägar. HMAC-journalerna ersätter inte oberoende releaseproveniens.
- Komplett manuell repo-/beroende-/licens-/SBOM-/ABI-audit, riktig Bubblewrap-provkörning, fysisk NPU-/ljudverifiering samt strömavbrottsrecovery på VENTUNO återstår.

**Status:** DRAFT / NO-GO för main eller deployment. Kräv komplett ARM64 source-only CI på exakt slutlig HEAD.
