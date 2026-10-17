# MyAI – fail-closed verifiering vid ändrad staging, source drift och ogiltig returkod (2026-10-17)

**Bas:** verifierad DRAFT PR #311, commit `c1ba7085dbef8bf727d925c6f4cc98e0a3085a0e`. Endast källkod och syntetisk ARM64 source-only CI. Ingen aktiv VENTUNO-installation, promotion, recovery eller merge till main.

## Pass 1 – kodflöde och säkerhetsfynd

`SelfDevVerifier.verify()` bygger kommandon som ska köras i Bubblewrap och samlar returvärden i `checks`. Före ändringen gjorde den `int(result.returncode)`; ett inkorrekt/malformat kommandoresultat som `"0"`, `0.1` eller `False` kunde därför tolkas som en framgångsrik process med exit-code 0. Processresultatet måste ha en faktisk heltalsreturkod, inte ett typkonverterat sant/falskt eller flyttalsvärde.

Funktionen samlade `changed_files()` före verifieringen och sparade samma `workspace_manifest_digest` efteråt, utan att kontrollera om kommandona ändrat staging under tiden. Den hämtade också `source_drift()` i slutet men beräknade `passed` enbart utifrån processernas returvärden och error-fält. Ett protokoll kunde därför få `passed=true` även när `source_drift` innehöll ändrade aktiva filer, eller staging-manifestet ändrats. Promotion hade en senare egen preflight som normalt blockerade detta, men `selfdev_verify.py` och andra läsare kunde rapportera ett falskt positivt verifieringsresultat.

## Pass 2 – förändring och tester

- Kräv `type(result.returncode) is int` för varje sandboxkommando, exakt som `subprocess.CompletedProcess.returncode`. Vid fel typ behandlas kommandot som misslyckat med `returncode=-1` och kontrollerat `TypeError`-spår. Inga ytterligare kommandon körs efter felet.
- Efter kommandokörningen skannas workspace igen med `changed_files()` och aktiv källkod med `source_drift()`. Manifestdigest och listorna `changed`, `added`, `deleted` måste vara identiska med snapshoten före sandboxkörningen för att `passed` ska kunna bli sant.
- Vid mismatch ges `error=` med explicit drifttext och `passed=False`. Om alla kommandon gav 0 men verifierarens integritetskontroller misslyckades sätts protokollets övergripande `returncode=-1`, så CLI inte visar falsk framgång.
- Behåll exakt den **ursprungliga** manifestdigests snapshot som kandidatens attestering. Detta är fortfarande en observation från lokal kod, inte en kryptografisk signatur.
- Fem nya testfunktioner (åtta parametervarianter sammanlagt): syntetisk stagingmutation under kommando, aktiv källkod som ändras under kommando, befintlig drift före kommando, `str/float/bool/None` som osäkra processreturer samt raderad stagingfil under verifiering.
- Tidigare verifierings- och promotionsintegrationer samt komplett ARM64-project suite ska köras mot exakt slutlig SHA.

## Kvarstående öppna blockerare

- Även ett fullständigt, internt konsekvent och passande protokoll i `verification.json` kan fabriceras av en process med **samma UID och skrivrätt** till sessionsfilerna. Den här PR:n bevisar inte att en betrodd Bubblewrap-körning har skett. För produktionssäker självmodifiering krävs oberoende attestering/processisolering med skilda privilegier, och att permissions/trust boundaries faktiskt verifieras på VENTUNO.
- Återläsning efter en verifiering förhindrar inte en icke-samarbetande skrivare från att ändra tillbaka alla bytes mellan kontrollerna eller efter avslut. Promotionens egna dirfd-hashkontroller, journaling och globala advisory-lock ska förbli aktiva.
- Komplett fil-för-fil- och beroende-/SBOM-/licens-/ABI-revision samt fysisk NPU-, ljud- och verklig strömavbrottsrecovery återstår. Inga merges eller installerade ändringar.

**Grind:** full ARM64 source-only GitHub Actions på exakt slutlig commit. Simulerade kommandon är inte fysisk verifiering.
