# MyAI — oberoende Ed25519-nyckelrotation och spärrlista: källkodsrevision

**Datum:** 2026-10-18. **Bas:** DRAFT PR #338, HEAD `aa9ebe5605b10eb2fddc3fbf5e2f331da2be8e85`. **Status:** endast källkodsprototyp / **PRODUKTION NO-GO**.

## Granskningspass 1: hotmodellen

PR #333–338 gav successivt verifierade Ed25519-signaturer, SQLite-baserat återspelsskydd, Unix-`SO_PEERCRED` och ett hostat integrationstest med fyra skilda Linux-UID där en oberoende verifierare själv körde riktig Bubblewrap före signering. Det här är ett test med syntetisk källa och tillfälliga nycklar. Produktionsnyckel, lagringsplats, återkallelse och nyckelbyte är **inte** definierade för VENTUNO.

En ny publik verifieringsnyckel får aldrig väljas från ett användar-/runtime-inskickat JSON-dokument. En angripare som får skriva i samma katalog som verifieringsresultat ska inte kunna byta betrodd nyckel, backa nyckelgenerationen eller återintroducera en återkallad nyckel. En gammal verifieringsnyckel och en ny nyckel som signerar samma rotationsförslag bevisar **inte** ett separat administrativt godkännande: gammal nyckel kan vara komprometterad. Rotation behöver därför godkännande av exakt förslagsdigest via en separat betrodd administrativ kanal och en uppdaterarägd monoton versionsräknare.

## Granskningspass 2: genomförd kod och regressionstester

`core/selfdev_verifier_key_rotation.py` är en **ren, skrivskyddad Ed25519-inspektionsmodul** utan privat nyckel, nyckelgenerering, databasanslutning, nätverk, processstart, filändring eller någon länk till `SelfDevPromotionManager`.

Modulen tar en utifrån pinnad `TrustedVerifierKey` med exakt 32-byte publik nyckel, positiv epoch och en **utifrån angiven betrodd, fryst spärrlista**. Nyckelidentiteten är SHA-256 över de råa publika nyckelbyten. Rotationsmeddelandet är begränsat till 4 KiB och har ett exakt schema; en kanonisk, domänseparerad representation förhindrar tvetydiga signaturtolkningar.

Ett rotationsförslag måste uppfylla samtliga följande krav:

- Den gamla nyckelidentiteten matchar den pinnade nyckeln och nuvarande generation; nästa generation måste vara **exakt +1**, inte samma eller hoppad.
- Det nya publika Ed25519-nyckelvärdet är exakt 32 byte, har matchande SHA-256-fingeravtryck, skiljer sig från det gamla och finns inte i spärrlistan.
- Nyckelbytet är bundet till en **extern** engångsutmaning från operatör/uppdaterare, ett avsiktligt begränsat tidsfönster (max 15 minuter), syfte `inspection-only-proposed-key-rotation` och mottagare `myai-updater-offline-key-review`.
- Exakt kanonisk payload-hash måste matcha ett **separat, utifrån godkänt** SHA-256-värde. Värdet får inte hämtas från rotationsdokumentet eller samma okontrollerade runtime-kanal.
- Både den *redan pinnade* gamla nyckeln och den föreslagna nya nyckeln måste ge giltiga Ed25519-signaturer över **samma** kanoniska, domänseparerade payload. Den nya signaturen demonstrerar endast innehav av tillhörande privat nyckel.
- Ofullständiga, dubbla, okända, manipulerade och för stora fält avvisas, liksom fel signatur, fel nonce, fel generation, fel nyckel, framtida/utgången period eller nyckel på spärrlistan.

Returtypen `RotationInspection` innehåller bara fingeravtryck/generation och håller `actual_key_rotation_performed=False`, `trusted_operator_approval_channel_verified=False`, `durable_epoch_storage_verified=False`, `authorizes_mutation=False` och `production_deployment_authorized=False`. Den kan således **inte** installera den nya nyckeln eller göra produktion redo.

Den separata hjälpmetoden `inspect_evidence_under_pinned_key` återanvänder PR #333:s Ed25519-verifiering, men tillåter inte ett oönskat `trusted_verifier_public_key`-argument som skulle kringgå det pinnade nyckelankaret. Den nekar också signerad evidens från en betrodd nyckel som uttryckligen spärrats.

`tests/test_selfdev_verifier_key_rotation.py` genererar endast tillfälliga privata testnycklar, prövar framgångsrikt dubbelsignerat **icke-auktoriserande** rotationsförslag och attacker med ensidiga signaturer, manipulerade signaturer/hashar, runtime-styrd nyckel, borttappad/återanvänd generation, ogiltigt tidsfönster, dubbla JSON-fält, okänt syfte, otillåtet operatörsgodkännande och spärrade nycklar. Testerna använder ingen riktig VENTUNO-nyckel.

## Väldigt viktiga ej uppnådda säkerhetskrav

1. **Ingen riktig nyckelprovisionering:** oberoende verifierar-UID, signerande nyckellagring/backup/rotation och verifierade ACL:er på VENTUNO saknas fortfarande. Den här inspektionsmodulen får inte själv läsa privata nycklar eller välja aktiv publik nyckel.
2. **Ingen autentiserad administrativ godkännandekanal:** ett `approved_payload_sha256`-argument räcker aldrig för att bevisa att användaren/administratören faktiskt godkänt rotationen. Det måste komma från en separat betrodd, auktoriserad källa med återspelningsskydd; detta är **inte** implementerat.
3. **Ingen beständig nyckelgeneration eller spärrlista:** anroparens `TrustedVerifierKey` är testdata/minnesvärden, inte ett verifierat kraschsäkert och rollback-skyddat register. Återkallelse måste genomföras i den skyddade uppdaterarens separata tillstånd eller genom betrott administrativt återställningsförfarande.
4. **Komprometterad föregående nyckel:** dubbelsignering hindrar inte en angripare som kontrollerar den gamla privata nyckeln och lyckas få operatörens godkännandekanal att godkänna ett falskt förslag. Säker incidentåterhämtning måste kunna stoppa verifiering helt och etablera ny trust root via ett separat fysiskt/administrativt förfarande.
5. **Inte kopplat till produktions-promotion:** inget testresultat eller rotationsbevis kan starta kodmutation. CI på hostade maskiner, även med riktig Bubblewrap, ersätter inte riktig VENTUNO- och fullständig MyAI-testplan.
6. **Historisk runner-risk kvarstår:** minst fem äldre GitHub-grenar pekar fortfarande på självhostad `ventuno-q` i sin källkod. GitHub runner group/admin access och den installerade Linux-UID/ACL-konfigurationen är inte verifierad eller spärrad.
7. **Riktiga hårdvaru- och återställningstester kvarstår:** NPU, ljud, Bluetooth, eMMC-strömavbrott, SQLite anti-rollback, systemd-servicehantering, SBOM/licens/ABI och annan fullständig revision.

**Acceptanskriterium för denna DRAFT:** grön full GitHub-hostad ARM64-källkodssvit på exakt slutlig HEAD. Godkända hostade tester betyder **inte** produktionsgodkännande. Ingen `main`-merge, ingen runnerdispatch till VENTUNO och ingen nyckel-/driftförändring på det fysiska kortet.
