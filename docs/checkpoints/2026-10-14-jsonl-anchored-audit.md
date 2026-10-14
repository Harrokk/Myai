# MyAI checkpoint — POSIX-katalogankrad revisionslogg (2026-10-14)

## Källkodsläge
- Aktiv draft-gren: `dev/jsonl-anchored-dirfd-20261014`
- Draft PR #135: https://github.com/Harrokk/Myai/pull/135
- Bas: tidigare draft PR #134, gren `dev/selfdev-orphan-snapshot-inspection-20261014`
- Senast gröna kodcommit: `88c13956efda4e2c933e7a8be42dbcc5c96f7fa2`
- Ingen merge till main. Ingen installation eller omstart av aktiv MyAI, GenieX eller annan VENTUNO-tjänst. Självuppdatering/promotion förblir avstängd.

## Bakgrund och risk
Förra audit-härdningen i PR #133 validerade symboliska länkar och vanliga filer innan loggning/rotation, men använde därefter fortfarande pathname-baserad filöppning och rename/unlink. En annan process kunde ändra en överordnad katalog i det korta fönstret efter preflight, så logghantering kunde hamna i fel katalog.

## Implementerad åtgärd i core/jsonl_log.py
- För POSIX-plattformar med `dir_fd`, `O_NOFOLLOW` och `O_DIRECTORY`: gå genom sökvägens komponenter från rotkatalogen med nofollow och behåll en öppnad katalog-fd under hela operationen.
- Kontrollera metadata för loggmål/roterade loggar via `os.stat(..., dir_fd=..., follow_symlinks=False)`. Avvisa icke-reguljära, hårdlänkade, felägda och osäkert skrivbara filer.
- Append använder `os.open` relativt den förankrade katalog-fd:n och verifierar öppnad fil via `fstat`; rotation använder `rename`/`unlink` med samma katalog-fd. Läsning använder också öppnad katalog/fildeskriptor, inte användarens efteråt utbytta sökväg.
- Efter operation jämförs ursprunglig katalogs sökväg med den öppna katalogens dev/inode; om katalogen bytts rapporteras fel (så obligatorisk audit kan neka åtgärden).
- Icke-POSIX-plattformar har kvar tidigare fallbackkontroller; motsvarande Windows-handle-implementation saknas ännu.

## Test
- GitHub Actions på riktig self-hosted VENTUNO Q ARM64, endast i temporär separat checkout: https://github.com/Harrokk/Myai/actions/runs/38547551507
- Resultat: **1598 passed, 6 skipped**, inklusive Python-källkompilering.
- Fyra nya regressionstester byter ut överordnad katalog mot symlink under append med rotation, append utan rotation, audit-läsning och direkt loggrotation. De verifierar att externa filer inte skrivs eller läses av fel och att operationen nekar katalogbyte.
- Kod utan nya tester verifierades separat: https://github.com/Harrokk/Myai/actions/runs/38547397508.
- Sex optional ONNX/NumPy-host-only-fall hoppades över på ARM64; de har tidigare verifierats i separat x86-hostad 22-testskörning: https://github.com/Harrokk/Myai/actions/runs/38520039444.

## Säkerhetsgränser och återstående arbete
- Skyddet gäller *parent-directory replacement* på POSIX. Andra processer kan fortfarande byta ut **filnamn inuti den förankrade katalogen** mellan metadata-kontroll och rename. Att helt förhindra sådana race kräver ytterligare filsystem-/privilegiedesign.
- `_path_lock` är per Python-process. Flera MyAI-processer som skriver/roterar samma audit-JSONL har ännu ingen gemensam interprocess-lock. Bör testas och härdas separat.
- Audit-fallback på Windows förblir mindre stark än POSIX-katalog-fd-fallet; inte likvärdiga säkerhetsgarantier.
- Ingen fysisk plötslig strömavbrottstest på VENTUNO eMMC är genomförd; fsync och syntetiska avbrott är inte bevis på full durabilitet.
- Projektets HMAC-nyckel skyddar inte mot en illvillig process med samma UID och full filåtkomst.
- Samtliga GitHub PRs är fortsatt draft, och historiskt cachad känslig SQLite-data behöver GitHub Support-hantering enligt blocker-PR #110 före huvudmerger.
- Windows Arduino App Lab invalid-board-IP-felsökning är fortsatt uppskjuten enligt tidigare användarönskemål.

## Nästa isolerade arbete
- Implementera och adversarialtesta en processgemensam säker rotationslåsmekanism på POSIX som inte kräver destruktiva åtgärder i aktiv installation.
- Granska race för final leaf-inode replacement under `rename` och hur obligatorisk audit ska fail-closed utan oavsiktlig användarfilsändring.
- Ingen autonom promotion/utplacering utan separat uttryckligt godkännande.
