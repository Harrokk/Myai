# MyAI — manuell säkerhetsgranskning av fil-workspace, 2026-10-17

**Bas:** PR #272, commit `b687bc836e1c866435d86629958c881e1b3d211c`. **Ändringsgren:** `dev/manual-audit-workspace-bounded-read-20261017`. **Status:** DRAFT, source-only; ingen ändring av installerade MyAI eller fysiska VENTUNO-tjänster.

## Granskat i två pass
- **Pass 1: funktion/logik och gränser:** full källtext för `modules/files/workspace.py` och `tests/test_file_workspace.py`; flöden för workspace-root, relativa sökvägar, kataloglistning, UTF-8-läsning, skrivning med temporär fil/atomär ersättning och audit-trail.
- **Pass 2: säkerhet/prestanda:** risk för minnes- och CPU-belastning, symlänkar, typ- och Unicode-fel, obehörig skrivning, katalogordning och tillämpning av resultatgränser. Full `core/deployment_lock.py` läst separat för att bedöma absolut sökvägshantering; dess operatörsstyrda trust boundary är **inte** slutattesterad.
- Detta är en avgränsad fördjupning, **inte** en fullständig manuell granskning av varje fil i projektet. Den befintliga 848-filsförteckningen har sin egen historiska Git-identitet och ändras inte retroaktivt.

## Bekräftade resursfynd och åtgärder

### FILE-RESOURCE-01 — inläsning före avkortning
Tidigare `read_workspace_text()` anropade `Path.read_text()` utan storleksgräns och avkortade resultatet efteråt. En mycket stor textfil kunde därför allokeras i sin helhet trots ett litet `max_read_chars`.

**Åtgärd:** text läses i fasta block om 16 384 Unicode-tecken. Endast upp till `max_read_chars` sparas för svaret; `total_chars` räknas under strömning så att befintligt returkontrakt (`content`, `truncated`, `total_chars`) bibehålls. Ogiltiga UTF-8-byte längre fram i filen avvisas fortfarande. Testerna kontrollerar att ingen obunden `read()` tillåts, att `total_chars` är korrekt även med multibyte-UTF-8 och att exact-limit inte räknas som trunkerat.

**Återstående begränsning:** exakta teckenantalet kräver att hela filen *läses sekventiellt*, och ett mycket stort indataflöde kan därför belasta disk/CPU under lång tid även om RAM-förbrukningen hålls nere. En separat tids-/storlekspolicy krävs om workspace-filer behandlas som fientliga eller obegränsade. Operatörsbegränsat konfigurerat `max_read_chars` ska kontrolleras före release.

### FILE-RESOURCE-02 — kataloggräns efter global sortering
Tidigare `list_workspace_files()` använde `sorted(root.rglob("*"))` på **alla** sökvägar innan `max_list_entries` tillämpades. En stor katalogstruktur kunde orsaka oproportionerlig RAM- och skanningstid.

**Åtgärd:** sortera en katalog i taget och gå djupet först i samma skiftlägesokänsliga fullsökvägsordning. Avsluta genereringen när antalsgränsen uppnåtts. Symboliska länkar ignoreras som tidigare. Regressionstester kräver både tidigt stopp före senare kataloger och oförändrad global alfabetisk ordning i ett gränsfall med fil/katalognamn som delar prefix.

**Återstående begränsning:** sortering av en *enskild* katalog kräver fortfarande minne proportionellt mot antal objekt direkt i den katalogen. Djup rekursion, katalogbyten under iteration och mycket långa filnamn behöver egna tester och hårdare gränser.

## Separata kvarstående säkerhetsfrågor (inte åtgärdade här)
- `resolve_workspace_path()` validerar `Path.resolve()` före filoperationen. En annan process med rätt att byta symlänkar i katalogträdet kan introducera en **TOCTOU-race** mellan validering och öppning/ersättning. Linux `dir_fd`/no-follow och isolerade katalogrättigheter bör prövas i en separat ändring; dessa två resursfixar är **inte** en fullständig filsystem-sandbox.
- `core/deployment_lock.resolve_project_path()` tillåter absoluta paths och normaliserar inte trust boundary; det kräver explicit granskning av anropare innan exponering för obetrodda indata.
- Läsfunktionens `path.is_file()` och efterföljande `path.open()` ligger också på olika tidpunkter. Ingen säkerhet hävdas mot en samtidiga fientlig process med filsystembehörighet.
- Kvarvarande icke-granskade repository-filer, full beroende-SBOM, nativa ABI/licenser, ljud, NPU/HTP, installation och rollback förblir **NO-GO**.

## Verifiering
Syntetiska pytest-tester är tillagda i `tests/test_file_workspace.py`. Slutlig full ARM64 source-only körning måste vara grön på **exakt sista commit** innan regressionspåståendet anses uppfyllt. Ingen fil utanför testernas temporära workspace ska skrivas av patchen; ingen produktionsinstallation, omstart, fysisk input eller merge är tillåten i denna DRAFT.
