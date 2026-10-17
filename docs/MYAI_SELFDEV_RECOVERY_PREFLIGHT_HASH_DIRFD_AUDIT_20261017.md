# MyAI – explicit recovery: no-follow-verifiering av aktiv kod före återställning (2026-10-17)

**Bas:** grön DRAFT PR #299 vid `1153cc24d010363ba163b9763935ad9670227dde`, full ARM64-test 3403 pass, 15 skip. Enbart källkodsändringar; ingen faktisk återställning på installerad VENTUNO.

## Granskningspass 1 – logik

`SelfDevPromotionManager._recover_interrupted_impl` kräver uttryckligt godkännande, globalt selfdev-lås och HMAC-verifierad journal. Före ändringen gjordes `target.is_file()` och `_sha256(target)` respektive `target.exists()` efter `_safe_project_target`. Därmed öppnades aktiva filnamn på nytt efter en separat säkerhetskontroll, och ett byte av exempelvis `core` till extern symlänk kunde omdirigera läsningen. Rutinen kan då felbedöma vilka filer som behöver återställas.

## Granskningspass 2 – säkerhetsförbättring

- Både befintliga och nytillagda kodfiler i recovery-preflight hashas nu via `_hash_existing_regular_path(target)`. Varje förälderkatalog öppnas `O_DIRECTORY|O_NOFOLLOW`, filen `O_NOFOLLOW|O_NONBLOCK` relativt katalogens FD. Vanlig fil och exakt en hårdlänk krävs, och hashen baseras på den öppnade inoden.
- För befintliga filer blockeras saknade/osäkra filer, symlänkar, hårdlänkar och felaktiga hashar före första återställningsskrivningen. För tillagda filer är frånvaro giltigt; en fil som finns måste vara säker och motsvara journalens efter-hash.
- Tre nya regressionstester: byte av `core` till extern symlänk efter vald målsökväg, byte av `tests/test_new.py` till extern symlänk mellan kontroll och hash, och avvisning av hårdlänkad aktiv fil.
- Journalsignatur, manuell fras, operationslås, revisionslogg och återställningssemantik i övrigt behålls; kräver full ARM64 source-only CI på exakt sista commit.

## Kvarstående releaseblockerande risker

- Hash-preflight och den efterföljande `_restore_from_backup`-åtgärden är **inte atomiskt sammanbundna**. En osamarbetsvillig skribent kan byta aktiv inode mellan kontroll och faktisk `_atomic_copy` eller filborttagning. Nästa steg bör binda varje filersättning till den förväntade observerade före-hashen och kontrollera gamla bytes direkt före ersättningen.
- Normal rollback, promotion-felstädning, OS-rättigheter och UID-isolering kräver fler kontroller. Advisory lock stoppar inte icke-samarbetsvilliga lokala skribenter.
- Komplett manuell fil- och beroenderevision, DNS/SSRF, SBOM, licenser, nativ ABI, riktig strömavbrottsåterställning samt fysiska VENTUNO/ljud/NPU-tester kvarstår.
- PR:n är DRAFT, ingen merge till main, ingen deployment, ingen aktiv selfdev på VENTUNO.

