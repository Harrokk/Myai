# MyAI – verifieringsprocess med Linux SO_PEERCRED (disposable prototyp)

**Datum:** 2026-10-18. **Bas:** DRAFT PR #334, commit 6dd93e1f31070a5635dd95819feccf4a76b65a8e.

**Status: REVISIONS- OCH TESTPROTOTYP. INGEN INSTALLATION, INGEN PROMOTION, NO-GO.**

## Första passet: nuvarande brist

PR #332 demonstrerade tre OS-identiteter i en tillfällig Docker-container; PR #333 verifierar externa Ed25519-signaturer och PR #334 demonstrerar ett transaktionsbaserat SQLite-register för engångsutmaningar. Ingen av dessa skapar en betrodd separat verifieringsprocess med faktisk Linux-identitet, skyddad privat nyckel och autentiserad lokal kommunikation. `verification.json` är fortfarande en post som kan förfalskas av en skrivare med samma UID. En godtycklig klient får aldrig kunna säga `passed=True` och få det signerat.

## Andra passet: kod och verkliga behörighetstester utanför enheten

`core/selfdev_unix_peercred.py` innehåller en liten källkodsmodul som:

- kräver ett lokalt Linux `AF_UNIX`-uttag och läser autentiska kernel-`SO_PEERCRED` med PID, UID och GID;
- avvisar klienter som inte motsvarar ett separat angivet betrott UID, utan att tolka några klientpåståenden om identitet;
- använder längdprefixerade binära ramar på högst 2048 byte och kräver strikt socket-timeout;
- tillåter bara schema v1 med `action=inspect_fixed_fixture` och 128-bitars hexkodad nonce: **inte** godkänd-status, sökvägar, kommandon, nycklar, UID-anspråk eller promotionsanrop;
- utför **ingen** processstart, bindning till socket, signering, verifiering av verkliga testresultat, promotion, GitHub-koppling eller installation.

`scripts/test_disposable_verifier_peercred_ipc.py` är ett separat experiment som körs endast under en uttryckligt begränsad Docker-miljö på GitHub-hostad Ubuntu. Där används fyra verkliga numeriska Linux-UID: updater 23001, runtime 23002, CI 23003 och oberoende verifierare 23004. Verifieraren äger en privat katalog (0700), läser själv en syntetisk testkälla, granskar dess Python-syntax och jämför mot en känd SHA-256-hash. Bara verifierarprocessen genererar en **slumpmässig engångs-HMAC-testnyckel** efter att ha bytt till UID 23004 och sparar den med mode 0600; de andra barnprocesserna kan inte läsa katalogen eller nyckeln.

Socket-filen är avsiktligt nåbar för de olika testidentiteterna, så att autentiseringskontrollen faktiskt prövas. Den använder alltså inte katalogens mode som ersättning för peerautentisering. Verifieraren avvisar runtime och CI enligt OS-`SO_PEERCRED`; även en updater med extra `passed=True` avvisas; en korrekt updaterförfrågan får bara ett `inspected_only`-svar med syntetisk fixture-hash och dummy-MAC som **inte** får användas till produktion. Anropsdata får inte välja testkommando, källa eller signerad status.

Workflow `.github/workflows/disposable-verifier-peercred-ipc.yml` kör endast på GitHub-hostad `ubuntu-24.04` och kontrollerar `runner.environment=github-hosted`, exakt commit-SHA och x86_64. Den startar en tids-/minnes-/processbegränsad Docker-container med nätverk avstängt, läs-only rotsystem, begränsade Linux capabilities, tmpfs och **två enskilda read-only Python-filer monterade**, aldrig VENTUNO:s projekt, enheter eller hemligheter. Workflow är endast push-triggad på denna DRAFT-gren och har `contents: read`. Vanlig GitHub-hostad ARM64-pytest verifierar både kernel-gränssnittsmodulen med fakes och källkodens fail-closed-krav utan att byta UID eller öppna en verklig socket.

## Vad detta INTE löser

- **Ingen verklig Ed25519-verifierartjänst:** HMAC:en i testet är avsiktligt en *dummy*, inte ett betrott produktionsbevis. Den publika nyckelkontrollen i PR #333 är fortfarande separat och ointegrerad.
- **Ingen oberoende observation av verkliga Bubblewrap-resultat:** statisk syntaxkontroll av ett förutbestämt test-fixture visar bara gränsen för processidentitet/privat nyckel.
- **Ingen produktions-IPC eller autentiserad uppdaterare på VENTUNO:** att en testklient har UID 23001 bevisar inte en fysisk installerad användare eller giltig promotion-approver. Samma UID eller root kan fortfarande låtsas vara en betrodd komponent om konto/separation saknas.
- **Ingen fysik / ingen durability:** inga egentliga ACL:er, GitHub runner-grupper, live `getfacl`, signeringsnyckelprovisionering, SQLite-krasch/filsystemåterhämtning, eMMC-strömavbrott, NPU, mikrofon, Bluetooth eller produktionsinstallation har testats.
- Gamla utvecklingsgrenar kan fortfarande peka mot självhostad `arduino`-runner och måste administrativt spärras innan riskfyllda grenar ändras.

**Fortsättning:** Koppla en uppdaterarägd, säker IPC-sessionsidentitet till en oberoende verifierare som *själv* startar och observerar all fastställd sandboxtestning och kan signera genom Ed25519 utan att låta CI/runtime läsa nyckeln. Knyt sedan till PR #334:s beständiga engångsregister, oberoende källhashar och mänsklig auktorisering före eventuellt godkännande av promotion. Kör granskning och fysiska tester före någon verklig migrering.

**Alltid DRAFT / produktionsspärr.** Ingen `main`-merge, ingen VENTUNO-åtgärd, ingen uppdatering eller promotion.
