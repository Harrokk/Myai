# MyAI – ogiltigförklara gamla selfdev-godkännanden före ny sandboxverifiering
**Datum:** 2026-10-18 · **Bas:** DRAFT PR #317, `1d32fa30582dc3373e67d8e8c734b511c0cbbe84` · **Utförande:** endast kodgranskning och GitHub-hostad, isolerad ARM64-CI

## Granskningspass 1: flöde och verifierat problem

`SelfDevVerifier.verify()` ska skapa ett nytt `verification.json` med faktisk kommandostatus, stagingmanifestets hash och sandboxens isoleringsinställningar. Efter tidigare revisioner är läsning, JSON-format, sessionsbindning och förväntade kommandolistor hårdare kontrollerade. Men den gamla verifieringsfilen ogiltigförklarades inte **innan** ett nytt verifieringsförsök började. Anropet till `workspace.changed_files()`, förbudet mot raderade stagingfiler samt `build_validation_commands()` / `build_command()` kunde kasta undantag innan den nya verifieringsrapporten sparades. Då fanns en gammal `passed: true` kvar, som kunde förväxlas med ett godkännande från det senaste försöket. Detta är ett auktorisations- och tillståndsproblem även när filen själv är giltig.

## Granskningspass 2: ändring och regressioner

- `verify()` anropar `workspace.invalidate_verification()` direkt vid start, **innan** `changed_files()`, byggnad av sandboxkommandon, filpreflight eller själva sandboxexekveringen. Funktionen är redan härdad: sessionens katalog öppnas med no-follow-dirfds; `verification.json` avlänkas relativt samma katalog; katalogen synkroniseras. Ett borttaget/verkligen saknat tidigare godkännande är ofarligt.
- Om ogiltigförklaringen misslyckas propagateras felet och ingen sandboxkörning startar. Vid förberedelsefel efter lyckad ogiltigförklaring blir det gamla godkännandet inte tillgängligt för efterföljande promotion.
- Verifieringen behåller normal rapportering av godkända eller misslyckade, faktiskt körda tester genom `save_verification()` och sina tidigare spärrar för källkodsdrift.
- Fem nya syntetiska regressioner: saknad Bubblewrap efter gammalt godkännande; raderad stagingfil före nytt test; saknat bash vid shell-validering; misslyckad ogiltigförklaring stoppar exekvering; nytt misslyckat test ersätter det gamla godkännandet med ett explicit `passed: false`-resultat.
- All gammal funktionalitet för promotion, rollback, verifieringsresultat och sessionsmetadata omfattas av hela testsviten.

## Säkerhetsgränser och NO-GO

- Detta fixar **kvarlämnat gammalt godkännande vid ett nytt försök**, inte kryptografiskt verifieringsursprung. Processer med samma användaridentitet och skrivbehörighet till sessionskatalogen kan fortfarande försöka skapa egna giltiga JSON-filer. Behörighetsseparation och signerade testattestationer kräver separat arkitekturbeslut.
- Om filsystemet förhindrar borttagning av ett gammalt godkännande avbryts verifieringen; den gamla filen kan då kvarstå och operatören måste åtgärda filsystemsfel. Ingen säkerhetsgaranti ges mot två icke-samarbetande, samtidigt startade verifierings- och promotionsprocesser. En projektglobal låsordning för dessa operationer bör granskas separat.
- Fullständig fil-för-fil-granskning, beroende-/SBOM-/licens- och ABI-revision, fysisk VENTUNO NPU/ljud och verkligt strömavbrott/recovery kvarstår.
- Körningen ska göras på **GitHub-hostad disponibel ARM64**, inte på produktionskontots VENTUNO-runner (se CI-isoleringen i PR #316).
- Ingen merge till main, ingen aktiv deployment eller självmodifiering; allt förblir DRAFT/NO-GO.

**Godkännandekrav:** fullständig isolerad ARM64-source-only CI på exakt slutlig SHA samt dokumenterade testresultat.
