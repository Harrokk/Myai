# MyAI – befintliga selfdev-sessioner: kontrollera UID och privata filer (2026-10-17)

**Bas:** grön DRAFT PR #316, commit `4c8f16a4d21bb9d5eb1b07d5d9cc89ab7fa0c332`. Enbart repo-källkod och source-only-testning på **GitHub-hostad ARM64**, inte på produktionsanvändaren på VENTUNO. Ingen aktiv migration, rollback, promotion, fysisk runtime eller merge berörs.

## Pass 1 – logik och säkerhetsfynd

`SelfDevWorkspace.create()` skapar nya sessioner med privat `0700`-katalog och `0600`-metadata. Tidigare `_session_directory_fd()` öppnade senare befintliga sessioner med `O_DIRECTORY|O_NOFOLLOW` i varje föräldraled, men kontrollerade inte UID eller faktiska permissions på den **öppnade session-inoden**. En importerad, ändrad eller ersatt katalog skulle alltså kunna användas som sessionsunderlag, även om den hade grupp-/världsaccess eller ägdes av annat UID. `_read_session_record()` kontrollerade vanlig fil, högst en hårdlänk och stabilitet under läsning, men inte UID eller privata permissions. `_write_session_record()` vägrade symlänkar/hårdlänkar före atomisk rename men saknade också dessa metadata-kontroller för tidigare befintlig fil.

Detta är en annan hotgräns än att JSON är giltig eller knuten till rätt sessions-ID. Innehåll kan vara korrekt formaterat men otillåtet åtkomligt eller ändringsbart via sitt filsystemläge.

## Pass 2 – implementerad ändring

- `_session_directory_fd()` använder befintlig no-follow-öppning, gör därefter `os.fstat(fd)`, kräver `S_ISDIR`, ägare lika aktuell `geteuid()` och **inga grupp-/världsbehörigheter** (`mode & 0o077 == 0`). Fel avvisas och filbeskrivaren stängs.
- `_read_session_record()` kräver före läsning att den faktiska JSON-inoden är vanlig fil, har `nlink==1`, tillhör aktuell UID och saknar grupp-/världsaccess (`mode & 0o077 == 0`). Filstorleks- och stabilitetskontroller från PR #309 behålls och kompletteras med en explicit jämförelse av UID och mode före/efter läsningen.
- `_write_session_record()` kräver motsvarande UID, filtyp, enstaka länk och privata permissions på **befintligt** `session.json`/`verification.json` före atomisk ersättning. En säker ny temporär fil använder fortsatt exklusiv `O_CREAT|O_EXCL|O_NOFOLLOW` och mode 0600.
- Ingen osäker befintlig session eller journal repareras tyst med `chmod/chown`. Vid avvikelse stoppas operationen innan en JSON-fil kan läsas eller ersättas.
- Fem nya regressioner: grupp-/världstillgänglig sessionskatalog, världsläsbar sessionsmetadata, gruppskrivbart verifieringsresultat, försök att skriva över osäkert befintligt verifieringsresultat med temporärfilstädning, samt normal privat session.
- De äldre testerna för dubbla JSON-fältnamn och NaN/Infinity får mode 0600 på **syntetiskt manipulerade JSON-fixtures** så de fortfarande testar själva parsningen, inte filpermissionsgrinden.

## Begränsningar och release-NO-GO

- Detta förhindrar användning av felaktigt öppnade sessioninoder, men en process med samma UID har fortfarande i princip möjlighet att manipulera sessionfiler och korrigera deras mode innan nästa öppning. Kontroll av filägarskap och rättigheter är **inte en signatur från en oberoende verifierare**.
- Legacy-sessioner med gamla permission-mönster kan behöva separat godkänd migration, inte automatisk reparation.
- CI-kod på GitHub-hostad ARM64 ger inte nödvändigtvis fysisk kompatibilitet med VENTUNO:s Qualcomm-drivrutiner. Gammal manuell 103-workflow-baslinje är fortsatt blockerad av den avsiktligt ändrade `tests.yml`. Ingen main-merge, produktionsdeployment eller ny manuell releaseattest tillåts.
- Omfattande repoaudit, beroenden/SBOM/licenser/nativ ABI, verklig bwrap-exekvering och VENTUNO audio/NPU/strömavbrotts-recovery återstår.

**Grind:** full GitHub-hostad ARM64 source-only CI på exakt slutlig PR-SHA, med den historiska workflow-driftspärren fortfarande fail-closed.
