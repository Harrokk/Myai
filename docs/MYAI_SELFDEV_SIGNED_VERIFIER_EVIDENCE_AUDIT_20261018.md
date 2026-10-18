# MyAI — oberoende signerade verifieringsbevis: read-only förkontroll

**Datum:** 2026-10-18. **Bas:** grön DRAFT PR #332, HEAD 86ab3f111c5b0b0bb87ea178052326796e41ef8a. **Status:** OFFLINE PROTOTYP, inte produktionsauktorisation.

## Pass 1: bekräftad säkerhetslucka

`core/selfdev_verify.py` utför Bubblewrap-tester, loggar återkommande kontrollsteg, verifierar manifestet efter körningen och sparar `verification.json`. `core/selfdev_promote.py` kräver detaljerade konsistenta fält i denna fil och kontrollerar kod/manifest. Båda använder ett gemensamt OS-lås mot **samarbetande** lokala skrivare. De mekanismerna skyddar inte mot en illvillig **samma-UID-process** som kan skriva i samma sessionskatalog och förfalska såväl metadata som den osignerade verifieringsposten. HMAC på promotion-journalen ligger också i den gamla lokala behörighetsdomänen och är inte ett oberoende verifieringsbevis.

PR #332 har verifierat tre numeriska Linux-UID och 19 nekade filåtkomster **enbart i en tillfällig Docker-container**. Den har inte konfigurerat en oberoende verifierare, skyddat riktiga nycklar eller flyttat produktionsprocesser på VENTUNO.

## Pass 2: implementation i DRAFT

`core/selfdev_signed_evidence.py` är en **ren läsande kontrollmodul** för Ed25519-signaturer, med `cryptography` som redan används i den isolerade CI-miljön. Den kan inte signera bevis, generera privata nycklar, spara sessioner, öppna OS-filer eller utföra promotion. Endast testkoden `tests/test_selfdev_signed_evidence.py` genererar tillfälliga privata testnycklar.

En signerad, kanoniskt kodad domänseparerad JSON-post binder exakt:

- En känd utfärdare `myai-independent-verifier-v1` och mål `myai-updater-inspection-only`, schema v1 och inspektion i stället för promotion.
- Unikt sessions-ID, SHA-256 över staging-manifest, testplan och verifierarens råbevis.
- Engångsutmaning/nonce med 128-bitars hexformat, som **uppdateringstjänsten måste skapa och lagra själv** (denna tjänst finns ännu inte).
- Början/slut för det signerade resultatet, högst fem minuters giltighet, sant godkänt resultat, `bubblewrap`, isolerat nätverk och inga host-enheter.
- En exakt 64-byte Ed25519-signatur som verifieras med en **utifrån betrodd, separat pinnad** rå publik nyckel. Bevisets JSON får inte leverera eller byta verifieringsnyckeln.

Okända/duplicerade fält, ogiltiga typer, icke-ändliga tal, för långa meddelanden, felaktiga signaturer, fel session/manifest/testplan/råbevis/nonce, återanvänd nonce i den *anroparlevererade* listan, framtida eller utgången tid avvisas. Nyckelordning påverkar inte signaturbytes eftersom den kanoniska representationen har sorterade nycklar, men exakta fält är obligatoriska.

Returtypen `EvidenceInspection` har **alltid** `authorizes_mutation=False`, `production_deployment_authorized=False`, `independent_verifier_execution_verified=False`, `source_provenance_verified=False` och `durable_anti_replay_verified=False`. Verifierad Ed25519-signatur och matchad kontext är **inte** bevis att själva testkörningen utfördes av en oberoende tjänst.

## Viktig designgräns / NO-GO

Det finns **ingen tjänst som signerar på rätt sätt** i denna PR. En tilltänkt betrodd signerare måste under en separat Linux-UID själv starta/observera rätt Bubblewrap-sandbox, kontrollera manifest och fullständig testplan mot verkliga data och använda en privat nyckel som inte kan läsas av runtime/CI/selfdev. Den får aldrig godkänna en från runtime inskickad `passed=True` bara genom att signera den.

Den privata nyckeln ska ligga hos verifieringstjänsten, den publika nyckeln ska vara pinnad av updatern via betrodd distribution. Ett durable, kraschkonsistent nonce-register hos updatern måste på säkert sätt reservera/konsumera utmaningar för att stoppa återspel efter omstart och samtidiga promotion-försök. **Modulen i detta steg är stateless och implementerar INTE ett sådant register.** Betrott aktuellt manifest/testplan/bevis måste dessutom samlas in från oberoende källa, inte från samma skrivbara `verification.json`.

Detta är ännu **inte kopplat** till `SelfDevPromotionManager`. Detta val är avsiktligt: att acceptera signerat men otillförlitligt indata, utan en separat verifierare och beständig replay-spärr, skulle skapa falsk säkerhet. Gamla historiska GitHub-grenar kan fortfarande få åtkomst till gamla VENTUNO-runnern. GitHub-administration och fysisk migrering återstår.

## Verifiering och fortsättning

Automatiska adversariella unit-tester kontrollerar manipulerade signaturer, främmande nycklar, annan session, ändrat manifest/bevis/testplan, dubbla JSON-fält, extra påståenden om promotion, datum och återspel; giltigt signerat testbevis ger bara icke-auktoriserande läsresultat.

**Följande krävs före realtids-test på VENTUNO:** en riktig separat verifieringsprocess, skyddad nyckeldistribution, säker IPC med motpartsidentitet, beständig nonce-lagring, oberoende råbevis/artefakt-hashar, tvåpass kod-/beroenderevision, fysiska NPU/ljud/strömavbrottstester och uttrycklig operatörsauktorisation. DRAFT, ingen main-merge, ingen produktionsdrift eller selfdev-promotion.
