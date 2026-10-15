# MyAI – Unicode-säker och samtidighetskontrollerad minnesgranskning

Datum: 2026-10-15. Utvecklingsgren `dev/ventuno-memory-review-unicode-whitespace-dedupe-20261015` ovanpå [PR #187](https://github.com/Harrokk/Myai/pull/187). Endast **DRAFT**; ingen merge, installation eller åtkomst till faktisk VENTUNO-minnesdatabas.

## Utgångspunkt

[PR #187](https://github.com/Harrokk/Myai/pull/187) är ett tidigare verifierat utkast som skilde auditloggfel efter faktisk minnes- eller granskningsköinsättning från fel innan skrivning. I `MemoryStore.enqueue_review` fanns redan `BEGIN IMMEDIATE` för att serialisera samtidiga försök, och atomisk sammanslagning av nya konflikt-ID:n, men avdubblieringen använde SQLite `lower(category)=lower(?)` och `lower(trim(content))=lower(trim(?))`.

SQLite `lower()` hanterar som standard inte hela svenska Unicode-skrivsättet och `trim()` hanterar bara ledande/avslutande standardmellanslag. Kandidater som `PRÄFERENS` kontra `präferens`, `Spara  en inställning` kontra `Spara en inställning`, eller Unicode NFC kontra NFD kunde därför skapa **två väntande granskningar** trots att de avser samma fråga. Ingen tidigare skadlig dublett har konstaterats i användarens faktiska databas.

## Korrigering

- `core/memory.py`: `_pending_review_key` skapar en **intern** jämförelsenyckel för kategori och innehåll med Unicode NFC, normaliserade interna whitespace-sekvenser och `casefold()`. Ursprungsinnehållet i databasen **ändras inte**; det är viktigt för användarens faktiska formulering och för senare spårbarhet.
- Under det **befintliga `BEGIN IMMEDIATE`-skrivlåset** hämtas en begränsad mängd väntande poster och jämförs i Python med samma nyckel. Senast insatt matchning återanvänds och redan existerande konflikt-ID:n kombineras med nya, som tidigare; den säkra spärren i `approve_review` hindrar direkt godkännande när konflikter finns.
- En gräns på **4096 väntande poster** för jämförelsen gör att en för stor kö leder till ett tydligt **NO-GO** snarare än att algoritmen tyst slutar söka och skapar en osynlig dublett. Detta är också ett operativt tak för att inte av misstag göra obegränsade dyrbara kögenomsökningar; en mycket stor verklig kö kräver separat, auktoriserad migrering/indexering.
- Avslutade/avvisade granskningar återanvänds **inte** som aktuellt pending; den historiska raden ligger kvar och en ny kandidat kan läggas till på normalt sätt. Olika innehåll och olika kategorier förblir separata.

## Isolerade tester

- [Riktad GitHub-hosted x86 CI #38692145983](https://github.com/Harrokk/Myai/actions/runs/38692145983): **SUCCESS, 38 passed** (8 nya regressioner plus befintliga minnesadministrations-/livscykeltester).
- Regressioner: svenska versaler/gemener inklusive `Ä`, Unicode NFC/NFD, osynlig NBSP och interna tabbar/nyrader, oförändrad sparad ursprungstext, distinkta betydelser och kategorier, samtidigt startade motsvarande förfrågningar, bevarad konflikteskalering, historiskt avvisat ärende och backlogtak med 4097 syntetiska poster.
- En första riktad CI misslyckades i **testets egen förväntan**: `list_reviews()` visar bara pending och tog därför inte med den redan avvisade raden. Testet rättades till att kontrollera den avvisade och nyinlagda posten med `get_review()` och SQLite-historik. Ingen ändring av produktionsbeteende krävdes för den testkorrigeringen.
- Fullständig isolerad ARM64-källkodstestning måste kontrolleras på **slutlig PR-HEAD** efter checkpoint-commit. Inga verkliga minnen, verktygsoperationer, kameror, mikrofoner eller modeller används.

## Begränsningar och följande steg

Köavdubbliering är **inte** automatisk återställning av historiskt skapade dubbletter. Stora äldre köer över 4096 pending granskas inte här och får en explicit felstatus. Minnesrensning av faktiskt användardata, dataåterställning och migrering till permanent unik normaliserad indexnyckel kräver separat riskgranskning.

Ingen ändring i live VENTUNO, SQLite-runtime, systemd/GenieX, firmware, rättigheter, USB-ljud, kamerafunktion, NPU/HTP/QNN/QAIRT, externa API-token, verktygseffekter eller PR-merge/deployment. [PR #110](https://github.com/Harrokk/Myai/pull/110) GitHub-historik och Support-cache-rensning är fortsatt separat releaseblockerare.
