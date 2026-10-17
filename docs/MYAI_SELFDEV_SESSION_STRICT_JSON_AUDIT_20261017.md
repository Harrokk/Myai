# MyAI – strikt JSON för selfdev-sessioner och verifieringsresultat (2026-10-17)

**Bas:** grön DRAFT PR #309, commit `e374a6225bffeb37cc3596acf8836920e3cd6880`. Endast repo-källkod och syntetisk ARM64 source-only testning. Ingen aktiv VENTUNO-installation eller main-merge ändras.

## Pass 1 – semantik och säkerhetsfynd

`SelfDevWorkspace._read_session_record()` används för `session.json` och `verification.json`, bland annat vid `SelfDevPromotionManager._verification()`. Efter PR #309 är läsningen filbeskrivarförankrad och stabil mot upptäckbara samtidiga skrivningar. Den fortsatte dock att använda `json.loads` utan särskilda verifieringsregler. Python accepterar **dubbla nycklar** och väljer det sista värdet, exempelvis `{"passed":false,"passed":true}`. Det kan ge olika tolkningar mellan granskning, logg, signering och framtida komponenter. `json.loads` accepterar också `NaN`, `Infinity` och `-Infinity`, vilka inte är standardenliga JSON-tal. Skrivvägen `json.dump` kunde producera dessa värden.

## Pass 2 – begränsad åtgärd

- Samma redan kontrollerade sessionfilbytes skickas till `json.loads` med `object_pairs_hook` som avvisar upprepade fältnamn **på varje nivå i JSON-objektet**, inte bara på toppnivå.
- `parse_constant` avvisar `NaN`, `Infinity` och `-Infinity` innan innehållet kan användas som sessionsmetadata eller verifieringsbeslut. Ogiltigt UTF-8 och för djupa parsningar ger kontrollerat `ValueError`.
- `_write_session_record` skriver nu med `json.dump(..., allow_nan=False)`, så MyAI inte själv genererar data som den strikta läsaren måste avvisa.
- Existerande filnamn, vanliga JSON-fältnamn, JSON-objektkravet, 4 MiB-gränsen, den stabila fd-läsningen från PR #309, exklusiva temporära filer och atomisk rename behålls.
- Fyra nya testfunktioner, varav en parametriserad med tre konstantfall: dubbla toppnivånycklar i verifiering, dubbla inre `baseline`-nycklar, alla tre icke-finita tal, samt avvisad skrivarutmatning utan att ett tidigare giltigt verifieringsresultat ändras.

## Kvarstående risker och NO-GO

- Strikt JSON ersätter **inte** bevis för att innehållet producerats av rätt verifieringsprocess. Någon med samma UID och skrivrätt till sessionskatalogen kan fortfarande försöka byta ut hela, giltiga JSON-filer. Verifieringsresultatets ursprung och bindning till faktisk sandboxkörning är ett eget releasekritiskt granskningsspår.
- OS-/behörighetsisolering, icke-samarbetande lokala skribenter, fullständig fil-för-fil-revision, beroende-/SBOM-/licensgranskning och fysiska VENTUNO/NPU/ljud-/strömavbrottstester återstår.
- Alla PR:er förblir DRAFT. Ingen merge till main, ingen live promotion, rollback, legacy-migrering eller utrullning.

**Verifiering:** full source-only ARM64 GitHub Actions på exakt slutlig PR-SHA krävs för grön status.
