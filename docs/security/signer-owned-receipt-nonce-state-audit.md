# MyAI – signerägt beständigt engångsregister för kvittoutställaren

**Datum 2026-10-19. Bas:** DRAFT #348 på commit `df5895c369b27f4926482055702a9183a67e3b39`. **Status: engångs- och UID-integrationsprototyp – produktion NO-GO.**

## Granskning, pass 1: kvarvarande dubbelutställanderisk

PR #347 visade att en separat Linux-UID (23006) kan läsa sina privata syntetiska vittnes-/SQLite-källor, själv verifiera signatur och journal, och sedan generera en Ed25519-kvittosignatur. Det fanns dock endast en **processlokal** boolesk variabel som hindrade att samma nonce signerades två gånger. Om processen startades om försvann spärren. Denna brist är oacceptabel för framtida separat verifierings-/kvittosignerare.

## Granskning, pass 2: ny kod och avgränsad integration

`core/selfdev_receipt_signer_nonce_ledger.py` ger en **kandidatbaserad** signerägd SQLite-tabell där varje 128-bitars nonce är primärnyckel. Varje förbrukning binds till enhet, avsikt, det signerade vittneshuvudets SHA-256, journalhändelsens SHA-256 och en högst 120 sekunder lång giltighetstid. Uppdateringarna kör `BEGIN IMMEDIATE` och `INSERT` utan upsert; en tidigare nonce nekas oavsett vilka nya argument som skickas. Om processen dör efter SQLite-commit, men innan den signerade Ed25519-kvittot, är noncen **fortfarande förbrukad**. Det ger fail-closed återhämtning, men innebär att en godkänd operatör behöver en separat manuell rutin för att utfärda en *ny* nonce efter ett avbrott.

`scripts/test_disposable_receipt_issuer.py` integrerar denna logik i den redan testade fyra-UID-miljön. Signeraren byter till sin egen UID innan SQLite-filen skapas under dess privata 0700-katalog med `umask(077)` och 0600 DB-fil. Den kontrollerar fortfarande verkliga kernel-`SO_PEERCRED`, vägrar klienternas `passed=True` och signerar först när den själv verifierat sina syntetiska vittnes-/journalfiler. **Innan** Ed25519-privatnyckeln används skriver den in förbrukningen i den egna separata SQLite-databasen. Ett andra anrop med samma nonce måste avvisas av databasen, inte av en tillfällig variabel.

`tests/test_selfdev_receipt_signer_nonce_ledger.py` använder endast test-SQLite och provar:
- en lyckad förbrukning följd av blockerat upprepat nonce med ändrat vittneshuvud;
- avvisad dubbelförbrukning efter stängning/återöppning av SQLite;
- två oberoende anslutningar där exakt en kan förbruka samma nonce;
- ogiltiga/överstora/negativa tider, felaktiga nyckelfingeravtryck och metadata utan delvis commit;
- en medveten negativ verifiering: ett återställt äldre SQLite-exemplar **kan** återanvända samma nonce när även ett separat monotont kontrollankare saknas.

Det nya `.github/workflows/disposable-signer-receipt-replay.yml` kör samma fyra-UID-kod på en tillfällig GitHub-hostad Ubuntu, med en exakt checkout-SHA och snävt distribuerade source-filer samt test-cryptography i separat temporär venv. Ingen VENTUNO-runner dispatchas. Source-only ARM64-tester kontrollerar dessutom att signerarens databasclaim sker **före** signaturen.

## Produktionsblockerare som kvarstår

- Detta är SQLite på en temporär VM, inte en långsiktigt provisionerad **VENTUNO-signerare**. Linux UID-isolering, filbehörigheter, nyckelbackup och systemd måste verifieras på den faktiska enheten.
- En angripare som kan återställa hela signerens SQLite-DB och dess trust-förankring kan fortfarande spela upp signering. Ett **separat skyddat, aktuellt monotont register** måste implementeras och testas med riktig disk-/strömavbrottsmodell.
- Den signerade kvittokedjan avser syntetiska testfiler. Ingen oberoende fysisk diskcommit/hårdvaruhändelse är bevisad. Att en signatur verifieras bevisar inte att riktig eMMC-logg blivit skriven.
- Ingen människas faktiska godkännande, automatisk kraschreparation, verklig verifierarnyckelrotation, production-promotion eller installerad tjänst är genomförd.
- PR #348:s GitHub-workflowinventering har hittat många självhostade auto-trigger-indikationer. Branchfilter och administratörsbehörigheter behöver granskas före varje fysisk test.

**Status:** enbart DRAFT, ingen merge till `main`, ingen ändring på VENTUNO. Exakt slutlig commit måste vara grön på GitHub-hostad ARM64 och separat fyra-UID-integration.
