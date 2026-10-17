# MyAI – sessionsskapande och staging i pinnade privata kataloger (2026-10-17)

**Bas:** DRAFT PR #306, exakt SHA `921e2298ef9cac8da0d3e6c613b7a41c704ea17f`. Ändringarna gäller endast källkod och isolerad ARM64 source-only CI; ingen installerad MyAI eller aktiv självmodifiering berörs.

## Pass 1: logik, säkerhet och identifierat fynd

`SelfDevWorkspace.create()` skapar nya sessionskataloger före att projektkoden kopieras till en privat stagingkatalog. Den äldre sekvensen `instance.session_root.exists()` följt av `instance.workspace_root.mkdir(parents=True,exist_ok=False)` öppnade kataloghierarkin flera gånger via pathname. Dessutom anropade `SelfDevWorkspace.__init__()` `base.resolve()` redan före kontrollen, vilket följde en eventuell symlänk i standardroten `runtime/selfdev`. En lokal skribent kunde flytta en tillåten katalog eller skapa en symlänk mellan kontroll, skapning och staging; skapning och senare källkopiering kunde därför ske i ett annat träd. `_session_directory_fd()` följde tidigare intermediära symlänkar eftersom `O_NOFOLLOW` endast skyddar sista pathnamekomponenten.

## Pass 2: implementation

- `__init__()` bevarar den absoluta **lexikala** sessionroten utan att följa `base`-symlänkar före säkerhetskontroll.
- `_new_private_session_workspace(session_root)` traverserar varje förälderkatalog från `/` via `O_DIRECTORY|O_NOFOLLOW`; saknade kataloger skapas via `os.mkdir(dir_fd=...)`. Den öppnade selfdev-föräldern måste tillhöra aktuell UID och sakna grupp-/världsskrivning.
- Sessionskatalogen och `workspace` skapas med `mkdir(dir_fd=...)`, exklusivt och med mode 0700. Befintligt namn (även dangling symlink) avvisas utan att återanvändas. Öppnade inoder kontrolleras via `fstat`; sessions-, workspace- och förälderkatalogerna `fsync`:as.
- Samma öppnade workspace-fd förblir pinnad under `_stage_source_files(...,target_dir_fd=...)`. Staging kan alltså inte omdirigeras med byte av förälderalias efter sessionsskapandet.
- `_session_directory_fd` öppnar nu även varje föräldraled via relativa `O_DIRECTORY|O_NOFOLLOW`-anrop innan sessionsmetadata läses/skrivs. Ett ompekat sessionsalias får inte leda metadatauppdateringar till extern katalog.
- Fem regressioner: privata sessions- och workspacebehörigheter, existerande symlinkad selfdev-root, runtime-parent-swap före öppning, sessionsnamn som redan är symlänk samt selfdev-aliasbyte efter att workspace-fd öppnats.
- Detta ändrar inte användarnas explicita sessions-ID, allowlistade stagingvägar, manifestformat, godkännandefras eller journal-/rollbacksemantik.

## Kvarstående releaseblockerande risker

- Projektroten är en operatorbetrodd fysisk katalog. Källkodsinläsning och övriga workspace-operationer behöver fortsatt konsekvent no-follow-ankring genom hela kataloghierarkin, inte enbart på sessions- och stagingkatalogerna.
- En icke-samarbetande process med rätt att byta projektets sessionsroot efter att katalogen öppnats kan fortfarande göra den publika pathname oanvändbar eller skapa ett annat sessions-ID i ett utbytt träd. UID-/filsystemisolering är ett självständigt driftskrav.
- Reella kraftavbrott, hårdvarans ljud/NPU och fullständig fil-för-fil-, beroende-/SBOM-/licensrevision återstår. Ingen merge till main, ingen aktiv installation eller live promotion.

**Krav:** full ARM64 source-only CI på exakt slutlig PR-SHA innan denna gren kallas testgodkänd.
