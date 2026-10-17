# MyAI – rensa ärvd miljö före Bubblewrap-verifiering (2026-10-17)

**Bas:** verifierad DRAFT PR #314, exakt SHA `e9f6b03d3718a07e5089a6d982e96f53f1b1ec6b`. Endast källkod och source-only ARM64-tester. Inga installerade processer, miljövariabler eller aktiva selfdev-sessioner på VENTUNO ändras.

## Pass 1 – konkret informationsflöde och fynd

`SelfDevVerifier._default_runner()` anropade `subprocess.run(command,...)` utan explicit `env`-argument. Därför ärvde själva Bubblewrap-startprocessen miljön från MyAI-processen, potentiellt med `OPENAI_API_KEY`, `GITHUB_TOKEN`, anpassad `PYTHONPATH`, `LD_PRELOAD` eller andra hemligheter/miljöinställningar. Även `SelfDevVerifier._sandbox_command()` specificerade bara några egna `--setenv`-värden, utan `--clearenv`; kvarvarande ärvda variabler kunde bli synliga för **obetrodd** testkod som körs i sandboxen. Nätverksisolering och PR #313:s readonly staging-mount skyddar inte mot utskrift i verifieringens loggar eller importpåverkan från en ärvd `PYTHONPATH`.

Bubblewrap stöder `--clearenv`: den tömmer miljön med undantag för `PWD` och nya efterföljande `--setenv`. Referens: https://github.com/containers/bubblewrap/blob/main/bwrap.xml , flaggan `--clearenv`.

## Pass 2 – skydd och kompatibilitet

- `_default_runner` skickar nu ett explicit begränsat `env`-objekt till `subprocess.run` med bara `PATH`, `HOME=/tmp`, `LANG=C.UTF-8` och `LC_ALL=C.UTF-8`. Inga tokens, `PYTHONPATH`, `LD_PRELOAD`, användarvariabler eller andra hemligheter kopieras från processen.
- Bubblewrap-kommandot lägger till `--clearenv` **före alla** `--setenv`. Efter `--chdir /workspace` anges `PWD=/workspace` uttryckligen eftersom `--clearenv` behåller tidigare `PWD`.
- Sandboxen får endast `HOME=/tmp`, `PWD=/workspace`, systemets deterministiska `PATH` och `C.UTF-8`-locale samt tidigare `PYTHONDONTWRITEBYTECODE`, privat `PYTHONPYCACHEPREFIX`, `XDG_CACHE_HOME` och `PYTEST_ADDOPTS=-p no:cacheprovider`.
- Readonly-kodmount, nätverks-/device-/PID-isolering, befintliga valideringskommandon, verifieringsformat och efterkörningshashkontroll förändras inte.
- Tre nya regressionstester plus justering i existerande isoleringstest: host-subprocess får inte ärva syntetisk hemlighet, `PYTHONPATH` eller `LD_PRELOAD`; sandboxkommandot måste ha `--clearenv` och bara explicita tillåtna variabler; **alla** syntax- och pytest-kommandon måste ha samma skydd och readonly-mount.

## Risker och verifieringsgrindar som kvarstår

- En explicit injicerad **anpassad `command_runner`** använder inte nödvändigtvis `_default_runner`. Ett lokalt program som byter `bwrap_path` till skadlig körbar fil kan fortfarande fånga miljö/argument; verifierarens binärintegritet och processidentitet kräver separat granskning och OS-isolation.
- Sandboxens faktiska `--clearenv`-beteende och testfunktionens beroende av rensad miljö är ännu **inte fysiskt testade på VENTUNO**. Korrekt kommandosträng plus syntetiska tester är inte bevis på fungerande runtime. Det är tänkbart att ett legitimt test tidigare förutsatte en ärvd systemvariabel; sådant ska lösas via en explicit tillåten, icke-hemlig variabel – **inte** via generell återärvning.
- Om en angripare kan manipulera `verification.json` eller sessionsrötter med samma UID kan värden fortfarande förfalskas; man kan inte kalla det kryptografiskt verifierad proveniens.
- Fortsatt release-NO-GO: fullständig manuell fil-för-fil- och beroende-/SBOM-/licensgranskning, lämplig betrodd identitet för sandboxbinary, fysiska ljud/NPU-tester och verkligt testad återställning efter strömavbrott.

**Status:** DRAFT, ej main-merge, ej live. Kräver full ARM64 source-only CI på exakt HEAD.
