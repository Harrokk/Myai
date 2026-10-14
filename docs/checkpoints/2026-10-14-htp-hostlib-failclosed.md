# MyAI – fail-closed-väljare för HTP-hostbibliotek, riktig VENTUNO

Datum: 2026-10-14. Gren: dev/ventuno-htp-hostlib-packaged-failclosed-20261014. **Endast DRAFT, ej driftsatt eller mergad.**

## Verifierad bakgrund

- [PR #167 verklig read-only-mätning #38605089142](https://github.com/Harrokk/Myai/actions/runs/38605089142): den gamla experimentella `_find_libraries()` väljer **annan dev/inode än QAIRT-paketets /usr/lib-fil för alla tre** `libQnnHtp.so`, `libQnnHtpV75Stub.so`, `libQnnModelDlc.so`. De korrekta `/usr/lib`-filerna finns på VENTUNO och är vanliga filer. Det bevisar inte exakt vilken historisk fil QNN-processen laddade när HTP initieringsfel inträffade, men visar en verklig brist i den nuvarande testkodens biblioteksväljare.
- Samma mätning: den syntetiska 16 004-byte-DLC-fixturen är intakt men **genererades med QAIRT 2.45**. VENTUNO har **qairt-libs och qairt-dsp-binaries 2.46.0-0ubuntu1~bpo24.04.1**, samma paketversion. Det är en skillnad men **inte** bevisad HTP-inkompatibilitet; CPU-körningen av DLC har lyckats.
- [PR #162, riktig selektor-jämförelse #38598267753](https://github.com/Harrokk/Myai/actions/runs/38598267753) visade även att den gamla DSP-Skel-väljaren hittade annan fil än officiellt paketerad Skel. [PR #163](https://github.com/Harrokk/Myai/pull/163) rättade den experimentella Skel-väljaren fail-closed, men ändringen är fortfarande ett utkast.
- Ingen HTP-inferens har lyckats eller verifierats. Firmware och DSP-processdomän är fortfarande inte kompatibilitetsverifierade; `backend_initialization_failure` är enda publicerade QNN-felkategorin från det senaste avgränsade försöket.

## Den nya korrigeringen

- `scripts/ventuno_tiny_qnn_htp_once.py::_find_libraries()` söker nu **inte** längre rekursivt i `ROOTS`, användarkataloger eller /opt-kopior. Den väljer endast tre exakt namngivna QNN-bibliotek direkt i `/usr/lib`.
- Den använder befintlig begränsad `inspect_resolved_skel()` (trots funktionsnamnet generellt ELF och dpkg-uppslag) för att kräva:
  1. Upplöst fil inom /usr och vanlig fil.
  2. AArch64 ELF-header, läst med fstat- och storlekskontroll.
  3. `dpkg-query -S`-paketägarskap som `qairt-libs`.
  4. Godkänt read-only-headerresultat.
- Om valideringen misslyckas för någon av de tre returneras den **inte**. Befintlig `run_once` kontrollerar att **alla** `LIBS` är identifierade och returnerar `no_go_required_htp_libraries` innan NPU-start om något saknas. Inga överblivna SDK-kopior används.
- Tre syntetiska tester kontrollerar strikt accepterad kanonisk fil, fail-closed för fel filtyp, arkitektur, paketägare och att den tredje filen stoppas även när de andra två är giltiga.
- `scripts/ventuno_strict_htp_hostlib_readonly.py` och branch/path-scopat GitHub-workflow gör bara metadata-kontroll med booleskt resultat på riktig VENTUNO, inte en HTP-körning.

## Begränsningar och nästa beslut

Korrigerad värdfilsidentitet minskar risken att experimentell testkod laddar fel ABI-version. Men det verifierar **inte** HTP-backendinitiering, exakt DLC 2.45 -> QAIRT 2.46 kompatibilitet, DSP-processdomän, firmware eller operatörsstöd. En uppfylld hostlib-gate får inte automatiskt starta någon HTP-körning; tidigare explicit opt-in, hårda resursgränser och separat säkerhetsgranskning gäller fortfarande.

**Inget nytt HTP/NPU-test, produktion-merge, sudo, chmod/chown, apt/udev/grupp/ACL-ändring, symlinkfix, serviceomstart, ljud eller kamera.** All kod är DRAFT. [PR #110](https://github.com/Harrokk/Myai/pull/110) historisk GitHub purge är separat blockerare.
