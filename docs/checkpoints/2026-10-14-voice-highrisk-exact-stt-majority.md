# MyAI checkpoint – obligatorisk oberoende STT-majoritet för högriskkommandon

Datum: 2026-10-14. Utvecklingsgren `dev/ventuno-voice-highrisk-exact-vote-20261014`, baserad på [PR #178](https://github.com/Harrokk/Myai/pull/178). **Endast DRAFT, ej driftsatt eller sammanslagen.**

## Utgångsläge

- [PR #178 full ARM64 CI #38632414122](https://github.com/Harrokk/Myai/actions/runs/38632414122): **2040 passed, 15 skipped**, statisk source/privacy-audit PASS med 0 blockerande fynd. HTP är avsiktligt avstängd mot aktiv GenieX. Ingen ny modellkörning.
- MyAI:s huvudmål omfattar tre oberoende taligenkännare och 2-av-3-majoritet för osäkra kommandon. Befintliga `core/voice_pipeline.py::choose_consensus` använde token-Jaccard/SequenceMatcher för *alla* transkriptioner och accepterade likhet över konfigurerad tröskel (normalt 0.62).
- Detta kan ge **falskt samma kommando** när tre högrisktolkningar delar många ord men skiljer sig i själva målet, exempelvis `Radera filen rapport ett`, `... rapport två`, `... rapport tre`. En tidigare spärr stoppade motstridiga nekandeord, men inte olika fil-/enhetsnamn.
- Det fanns dessutom konfigurationsvägar som kunde minska redundansen till två (eller helt avaktivera den) trots högrisk, en semantisk reservfunktion som kunde kringgå STT-majoriteten om uttryckligen påslagen, och möjlighet att skicka samma STT-instans flera gånger i backup-listan.

## Korrigering

- Vid jämförelse där **endera** transkriptionen är riskklassad som högrisk krävs **exakt samma normaliserade text** för att rösten ska räknas som samstämmig. Fuzzy-matching används *endast* mellan två lågrisktolkningar. Två liknande ofarliga frågor kan därmed fortfarande vinna mot en avvikande högrisktolkning utan att den farliga tolkningen får felaktig röst.
- Den befintliga oenighetsspärren för explicit negation fortsätter att neka riskfyllda, motstridiga uttryck oavsett majoritet. En ensamt läst högriskfras godtas inte som konsensus av `choose_consensus`.
- `VoicePipeline._needs_redundancy` kräver nu redundans för högrisk **oavsett `redundancy_enabled`**. `redundant_transcript_count` kan inte sättas till lägre än **tre** för högrisk. De två separata backup-STT-instansobjekten måste vara olika varandra **och primär-STT**; en och samma instans får inte utgöra flera röster.
- `semantic_consensus_for_high_risk` får inte kringgå den strikta transkriptmajoriteten. Semantisk reservfunktion för vanliga lågriskfrågor är oförändrad.
- Även om primär röstbekräftelse för ett redan väntande kommando har hög konfidens gäller befintlig explicit bekräftelsepolicy. Om den **saknar** tillräcklig konfidens och tre STT-röster används måste backup-rösterna komma från separata STT-instanser – duplicerade objekt får inte förfalska majoritet. Bekräftelselagret är inte ersatt eller kopplat förbi.
- Råa ljuddata, privata användarkommandon, modellvikter eller inspelningar ingår inte i tester eller checkpoint.

## Syntetiska regressioner, endast isolerat test

Nya tester täcker olika fil-/målord med hög Jaccard, två exakt överensstämmande högriskröster, olika frasering, bibehållen tolerant lågriskmajoritet, inget assistentanrop vid högriskkonflikt, duplicerade STT-instanser och primär-STT återanvänd som backup, duplicerad lågkonfidensbekräftelse, minst tre röster även när konfigurerat 2 eller redundans av, samt blockerad semantisk kringgång.

GitHub Actions använder dels ordinarie **isolerade VENTUNO ARM64 CI**, dels en path- och branch-avgränsad **GitHub-hostad x86**-workflow med temporär miljö och syntetiska STT-resultat. Varken mikrofon, QNN, GenieX, nätverksmodell, ljudkort eller HTP körs.

## Risker och gränser

Exakt normaliserad högrisktext är konservativ; två rimliga men språkligt olika transkriptioner kan kräva förtydligande i stället för att exekvera. Detta är avsiktligt. Såväl effekt-/verktygsplanbedömning som befintlig bekräftelse krävs fortsatt där de är konfigurerade. Säkerhetsklassificering är heuristisk och verifierad högriskkonsensus ersätter **inte** åtkomstkontroller för verktyg eller användarauktorisation.

**Ingen** produktion, firmware, permission/udev/grupp, service, ljud, kamera, USB, modellnedladdning, HTP/CPU-inferens, Qualcomm Cloud eller PR-merge på Ventuno ingår. Historisk GitHub Support/secret-history-purge [PR #110](https://github.com/Harrokk/Myai/pull/110) är fortfarande separat releaseblockerare.
