# MyAI – verifierbar granskning av källkod och DNS/SSRF, delrapport

Datum: 2026-10-17.
Källkod: DRAFT #271 ovanpå DRAFT #270.
Inga ändringar installerade på aktiv VENTUNO.

## Vad som faktiskt är gjort

Hela Git-trädet har inventerats och fått en granskningsnivå med individuell Git-blob-identitet i docs/MYAI_COMPLETE_FILE_REVIEW_LEDGER_20261017.md. Vid inventeringspunkten ingick 848 filer: 8 fulltextlästa säkerhetsfiler, 114 källhämtade och riskmönstergranskade filer och 726 ytterligare filer med enbart automatiska tidigare syntax-/test-/källscanningsresultat. Den efterföljande djupgranskningen höjde internet/search och internet/research till totalt 10 DEEP samt 112 SCREENED. Nya DRAFT-filer tillkommer efter denna punkt och behöver få en ny manifestbaslinje före slutligt releasebeslut.

En bokstavligt fullständig fil-för-fil och rad-för-rad-granskning av hela projektet kan alltså INTE attesteras utifrån dessa data. Detta är ett mätbart revisionsunderlag, inte en falsk fullständighetsstämpel.

Källtext för alla ordinarie core/ Pythonfiler utom paketets init-fil samt 45 centrala modules/ filer har hämtats och granskats mot riskindikatorer (nätverk, dynamisk import, subprocess, process-/fileffekt, symlinks, undantagsläckor). Komplett funktion-för-funktion kontroll kvarstår även i dessa SCREENED-filer. Separat prioriterad djupgranskning omfattade direkt berörda DNS- och internetverktyg.

## Prioriterade fynd med ändring

### Fynd SEC-01 (HIGH): DNS rebinding / SSRF
Före fix kontrollerade PublicWebClient DNS A/AAAA, men requests.Session.get använde egen senare DNS och kunde skicka en HTTP-begäran till lokal eller privat service INNAN anslutningens IP kontrollerades. En privat response-blockering var för sent. Kodfix i core/public_web_client.py och nya core/public_web_transport.py binder direkt till granskad numerisk global IP, kontrollerar peer före request och verifierar HTTPS-kedja/värdnamn/SNI med originalnamn. Proxy- och ny-DNS-väg används inte. Varje redirect granskas igen. Injektion av godtyckliga externa sessioner nekas som standard och kräver unsafe_test_session=True, endast för syntetiska tester.

Verifiering är offline-mockade socket/TLS/HTTP-tester som demonstrerar ingen request vid felaktig privat peer, blandade DNS-svar, redirect mot lokal tjänst och DNS-omslag på andra hoppet. Inga live privata endpoints testades.

### Fynd SEC-02 (MEDIUM): undantagsläcka från internetverktyg
Manuell källkontroll hittade rå exception-text i sök, research, prisjämförelse, väder och källgranskning. En nackdel var att exception från HTTP-transport eller extern modul kan bära interna sökvägar, användarfrågor eller tokens och återges ordagrant. Samtliga fem user-facing funktioners högsta undantagsgräns visar nu endast feltext dold. Syntetiska tester injicerar tokens och privata paths som inte får synas i svar.

### Fynd AUD-01 (LOW): otillräcklig manuell signatur
Tidigare automatiska tvåpassrevisioner täcker AST/syntax, många riskmönster och en full ARM64 pytest-svit, men motsvarar inte en verifierad manuell läsning av varje fil. Ett samlat och öppet file-ledger har skapats. Resten återstår.

## Övriga observationer från selektiv manuell läsning

- core/deployment_lock.resolve_project_path accepterar absoluta sökvägar utan tillåten målrot. Koden bör endast användas med betrodda operatörsparametrar; ett publikare anrop kräver destinationspolicy.
- modules/files/workspace.py använder kontrollerad och begränsad workspace-sökväg, temporär exklusiv fil och atomär rename. Ändrade överordnade katalogers symlinks/race mot en osäker aktör med samma filsystembehörighet bör testas separat.
- modules/internet/search.py talar mot en konfigurerad SearXNG-server; standard localhost:8080 är avsiktlig betrodd lokal trafik. Separera den tydligt från publik användar-URL via PublicWebClient.
- Local Ollama/GenieX API-anrop baseras på förkonfigurerad betrodd server och omfattas inte automatiskt av publika URL-socketpinningen; aktiva runtime-värden för dem är inte attesterade.
- Sidans sociala metadata, externlänkar och innehållsanalyser är konsumenter av redan hämtad HTML, inte nya oberoende nätverksanslutningar.

## Kvarvarande granskningskriterier

1. Slutför MANUELL fil-/funktionsgranskning av varje INDEXED och SCREENED i file ledger, inklusive tester, docs, YAML, deploy och firmware, med radintervall och separat oberoende peer-check. Att en fil finns i Git-trädet eller har syntaxvaliderats räcker inte.
2. Verifiera övriga wrapper-fel, processgränser, atomära filoperationer och självmodifierings-/permission-moduler i en komplett källtextbaserad hotmodellsgranskning.
3. Gör separat riktig HTTPS-via-numerisk-IP + CA-test i isolerad nätmiljö när säkerhetspolicy tillåter. Offlinetesterna bevisar kodflöde men inte verkliga OS-proxy/firewall/IPv6-varianter.
4. Komplett beroende-/SBOM/OS/native/QAIRT och licenser samt hela installerade voice-venv innan release.
5. Fysisk USB-mikrofon/TTS/NPU/Stop och oberoende rollback kräver operatörsmedverkan och särskilt samtycke.

Resultat: högprioriterad DNS/SSRF-kodrisk är åtgärdad och regressionssäkrad i DRAFT. Den omfattande MANUELLA revisionen är fortfarande öppen; produktion och main-merge är fortfarande NO-GO.
